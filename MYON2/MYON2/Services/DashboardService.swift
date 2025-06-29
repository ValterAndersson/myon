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
    
    // Loop prevention
    private var lastFetchAttempt: [String: Date] = [:]
    private let minTimeBetweenFetches: TimeInterval = 10 // 10 seconds minimum between fetches
    private var fetchAttemptCount: [String: Int] = [:]
    private let maxFetchAttempts = 3
    
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
                
                // Check if cached data is recent enough AND not empty
                let cacheAge = Date().timeIntervalSince(cachedData.lastUpdated)
                if cacheAge < shortTTL && !cachedData.isEmpty {
                    return cachedData
                }
                
                // If data is empty, always fetch fresh data (but with safeguards)
                if cachedData.isEmpty {
                    logger.info("Cached data is empty, will attempt fresh fetch")
                    do {
                        return try await fetchAndCacheDashboard(userId: userId, weekCount: weekCount)
                    } catch {
                        logger.error("Failed to fetch fresh data after empty cache: \(error)")
                        // Return the empty cached data as last resort to prevent crash
                        return cachedData
                    }
                }
                
                // Return non-empty cached data but refresh in background for next time
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
        
        // Also clear fetch attempt tracking for this user
        let keysToRemove = fetchAttemptCount.keys.filter { $0.hasPrefix(userId) }
        for key in keysToRemove {
            fetchAttemptCount.removeValue(forKey: key)
            lastFetchAttempt.removeValue(forKey: key)
        }
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
        let fetchKey = "\(userId)_\(weekCount)"
        
        // Check if we're fetching too frequently (loop prevention)
        if let lastAttempt = lastFetchAttempt[fetchKey] {
            let timeSinceLastAttempt = Date().timeIntervalSince(lastAttempt)
            if timeSinceLastAttempt < minTimeBetweenFetches {
                logger.warning("Fetch attempted too soon after last attempt. Time since last: \(timeSinceLastAttempt)s")
                throw DashboardServiceError.invalidData
            }
        }
        
        // Check if we've exceeded max attempts
        let attemptCount = fetchAttemptCount[fetchKey] ?? 0
        if attemptCount >= maxFetchAttempts {
            logger.error("Max fetch attempts (\(maxFetchAttempts)) exceeded for \(fetchKey)")
            fetchAttemptCount[fetchKey] = 0 // Reset for next time
            throw DashboardServiceError.invalidData
        }
        
        // Update attempt tracking
        lastFetchAttempt[fetchKey] = Date()
        fetchAttemptCount[fetchKey] = attemptCount + 1
        
        logger.info("Fetching fresh dashboard data for user: \(userId) (attempt \(attemptCount + 1))")
        
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
            
            logger.info("Fetched dashboard data - Current week: \(currentWeek != nil), Recent stats count: \(recentStats.count), User goal: \(userGoal ?? -1)")
            
            // Validate and cache only non-empty, valid data
            if !dashboardData.isEmpty && validateDashboardData(dashboardData) {
                let cacheKey = makeCacheKey(userId: userId, weekCount: weekCount)
                await cacheManager.set(cacheKey, value: dashboardData, ttl: longTTL)
                
                // Reset attempt counter on successful non-empty fetch
                fetchAttemptCount[fetchKey] = 0
                logger.info("Successfully cached valid non-empty dashboard data")
            } else if dashboardData.isEmpty {
                logger.warning("Skipping cache for empty dashboard data to prevent loops")
            } else {
                logger.error("Skipping cache for invalid dashboard data")
            }
            
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
    
    // Data validation to prevent caching invalid data
    private func validateDashboardData(_ data: DashboardData) -> Bool {
        // Check for reasonable data limits
        if let stats = data.currentWeekStats {
            // Sanity checks - no one does 1000 workouts in a week
            if stats.workouts > 100 || stats.totalSets > 10000 || stats.totalReps > 100000 {
                logger.error("Dashboard data failed validation - unrealistic values detected")
                return false
            }
        }
        
        // Check that we have reasonable number of recent stats
        if data.recentStats.count > 52 { // More than a year of weekly data
            logger.error("Dashboard data contains too many weeks of data: \(data.recentStats.count)")
            return false
        }
        
        return true
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