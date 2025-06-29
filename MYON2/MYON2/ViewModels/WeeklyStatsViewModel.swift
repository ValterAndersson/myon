import Foundation
import OSLog

@MainActor
class WeeklyStatsViewModel: ObservableObject {
    @Published var stats: WeeklyStats?
    @Published var recentStats: [WeeklyStats] = []
    @Published var frequencyGoal: Int?
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var hasError = false
    
    private let logger = Logger(subsystem: "com.myon.app", category: "WeeklyStatsViewModel")
    private let dashboardService: DashboardServiceProtocol
    
    init(dashboardService: DashboardServiceProtocol? = nil) {
        self.dashboardService = dashboardService ?? DashboardServiceManager.shared.getDashboardService()
    }
    
    func loadDashboard(weekCount: Int = 8, forceRefresh: Bool = false) async {
        logger.debug("Loading dashboard with weekCount: \(weekCount), forceRefresh: \(forceRefresh)")
        
        isLoading = true
        clearError()
        
        do {
            let dashboardData = try await dashboardService.loadDashboard(
                weekCount: weekCount,
                forceRefresh: forceRefresh
            )
            
            // Update published properties
            stats = dashboardData.currentWeekStats
            recentStats = dashboardData.recentStats
            frequencyGoal = dashboardData.userGoal
            
            logger.info("Dashboard loaded - Stats: \(stats != nil), Recent count: \(recentStats.count), Goal: \(frequencyGoal ?? -1)")
        } catch {
            logger.error("Failed to load dashboard: \(error)")
            setError(error.localizedDescription)
        }
        
        isLoading = false
    }
    
    func retry() async {
        await loadDashboard(forceRefresh: true)
    }
    
    func clearCache() async {
        guard let userId = AuthService.shared.currentUser?.uid else { return }
        logger.info("Clearing dashboard cache for user")
        await dashboardService.invalidateCache(for: userId)
    }
    
    // Keep old method for backward compatibility
    func loadCurrentWeek() async {
        await loadDashboard(weekCount: 1, forceRefresh: false)
    }
    
    private func setError(_ message: String) {
        errorMessage = message
        hasError = true
    }
    
    private func clearError() {
        errorMessage = nil
        hasError = false
    }
}

