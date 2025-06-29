import Foundation
import OSLog

// MARK: - Dashboard Data Model
struct DashboardData: Codable {
    let currentWeekStats: WeeklyStats?
    let recentStats: [WeeklyStats]
    let userGoal: Int?
    let lastUpdated: Date
    
    var isEmpty: Bool {
        currentWeekStats == nil && recentStats.isEmpty
    }
}

// MARK: - Dashboard Service Error
enum DashboardServiceError: LocalizedError {
    case userNotAuthenticated
    case dataFetchFailed(Error)
    case cacheFailed(Error)
    case invalidData
    
    var errorDescription: String? {
        switch self {
        case .userNotAuthenticated:
            return "User must be authenticated to load dashboard"
        case .dataFetchFailed(let error):
            return "Failed to fetch dashboard data: \(error.localizedDescription)"
        case .cacheFailed(let error):
            return "Cache operation failed: \(error.localizedDescription)"
        case .invalidData:
            return "Invalid dashboard data received"
        }
    }
}

// MARK: - Dashboard Service Protocol
protocol DashboardServiceProtocol {
    func loadDashboard(weekCount: Int, forceRefresh: Bool) async throws -> DashboardData
    func invalidateCache(for userId: String) async
    func preloadDashboard() async
}

// MARK: - Dashboard Service Implementation
@MainActor
class DashboardService: DashboardServiceProtocol {
    private let logger = Logger(subsystem: "com.myon.app", category: "DashboardService")
    private let analyticsRepository: AnalyticsRepository
    private let userRepository: UserRepository
    private let cacheManager: CacheManagerProtocol
    
    // Cache configuration
    private let cacheKeyPrefix = "dashboard"
    private let shortTTL: TimeInterval = 300 // 5 minutes for frequently changing data
    private let longTTL: TimeInterval = 3600 // 1 hour for stable data
    
    init(
        analyticsRepository: AnalyticsRepository = AnalyticsRepository(),
        userRepository: UserRepository = UserRepository(),
        cacheManager: CacheManagerProtocol = CacheManager()
    ) {
        self.analyticsRepository = analyticsRepository
        self.userRepository = userRepository
        self.cacheManager = cacheManager
    }
    
    // MARK: - Public Methods
    
    func loadDashboard(weekCount: Int = 8, forceRefresh: Bool = false) async throws -> DashboardData {
        guard let userId = AuthService.shared.currentUser?.uid else {
            throw DashboardServiceError.userNotAuthenticated
        }
        
        let cacheKey = makeCacheKey(userId: userId, weekCount: weekCount)
        
        // Try cache first unless force refresh
        if !forceRefresh {
            if let cachedData = await cacheManager.get(cacheKey, type: DashboardData.self) {
                logger.debug("Returning cached dashboard data for user: \(userId)")
                
                // Check if cached data is recent enough
                let cacheAge = Date().timeIntervalSince(cachedData.lastUpdated)
                if cacheAge < shortTTL {
                    return cachedData
                }
                
                // Return cached data but refresh in background for next time
                Task.detached { [weak self] in
                    try? await self?.fetchAndCacheDashboard(userId: userId, weekCount: weekCount)
                }
                
                return cachedData
            }
        }
        
        // Fetch fresh data
        return try await fetchAndCacheDashboard(userId: userId, weekCount: weekCount)
    }
    
    func invalidateCache(for userId: String) async {
        logger.info("Invalidating dashboard cache for user: \(userId)")
        let pattern = "\(cacheKeyPrefix)_\(userId)"
        await cacheManager.invalidate(matching: pattern)
    }
    
    func preloadDashboard() async {
        guard let userId = AuthService.shared.currentUser?.uid else { return }
        
        logger.info("Preloading dashboard data for user: \(userId)")
        
        // Preload common week counts
        let commonWeekCounts = [4, 8, 12]
        
        await withTaskGroup(of: Void.self) { group in
            for weekCount in commonWeekCounts {
                group.addTask { [weak self] in
                    _ = try? await self?.loadDashboard(weekCount: weekCount, forceRefresh: false)
                }
            }
        }
    }
    
    // MARK: - Private Methods
    
    private func fetchAndCacheDashboard(userId: String, weekCount: Int) async throws -> DashboardData {
        logger.info("Fetching fresh dashboard data for user: \(userId)")
        
        do {
            // Parallel fetch all required data
            async let currentWeekTask = fetchCurrentWeekStats(userId: userId)
            async let recentStatsTask = analyticsRepository.getRecentWeeklyStats(
                userId: userId,
                weekCount: weekCount
            )
            async let userGoalTask = fetchUserGoal(userId: userId)
            
            // Await all results
            let (currentWeek, recentStats, userGoal) = try await (
                currentWeekTask,
                recentStatsTask,
                userGoalTask
            )
            
            let dashboardData = DashboardData(
                currentWeekStats: currentWeek,
                recentStats: recentStats,
                userGoal: userGoal,
                lastUpdated: Date()
            )
            
            // Cache the results
            let cacheKey = makeCacheKey(userId: userId, weekCount: weekCount)
            let ttl = dashboardData.isEmpty ? shortTTL : longTTL
            
            await cacheManager.set(cacheKey, value: dashboardData, ttl: ttl)
            
            // Preload related data in background
            Task.detached { [weak self] in
                await self?.preloadRelatedData(userId: userId, weekCount: weekCount)
            }
            
            return dashboardData
        } catch {
            logger.error("Failed to fetch dashboard data: \(error)")
            throw DashboardServiceError.dataFetchFailed(error)
        }
    }
    
    private func fetchCurrentWeekStats(userId: String) async throws -> WeeklyStats? {
        // Try current week first
        if let currentWeek = try await analyticsRepository.getCurrentWeekStats(userId: userId) {
            return currentWeek
        }
        
        // Fall back to last week if current week has no data
        return try await analyticsRepository.getLastWeekStats(userId: userId)
    }
    
    private func fetchUserGoal(userId: String) async throws -> Int? {
        let attributes = try await userRepository.getUserAttributes(userId: userId)
        return attributes?.workoutFrequency
    }
    
    private func preloadRelatedData(userId: String, weekCount: Int) async {
        // Preload adjacent week counts
        let adjacentCounts = [weekCount - 4, weekCount + 4].filter { $0 > 0 && $0 <= 52 }
        
        for count in adjacentCounts {
            let cacheKey = makeCacheKey(userId: userId, weekCount: count)
            if await cacheManager.get(cacheKey, type: DashboardData.self) == nil {
                _ = try? await fetchAndCacheDashboard(userId: userId, weekCount: count)
            }
        }
    }
    
    private func makeCacheKey(userId: String, weekCount: Int) -> String {
        "\(cacheKeyPrefix)_\(userId)_weeks_\(weekCount)"
    }
}

// MARK: - Dashboard Service Manager (Singleton)
@MainActor
class DashboardServiceManager {
    static let shared = DashboardServiceManager()
    private let service: DashboardServiceProtocol
    
    private init() {
        self.service = DashboardService()
    }
    
    func getDashboardService() -> DashboardServiceProtocol {
        return service
    }
    
    // Convenience method for cache invalidation on workout updates
    func invalidateDashboardCache() async {
        guard let userId = AuthService.shared.currentUser?.uid else { return }
        await service.invalidateCache(for: userId)
    }
} 