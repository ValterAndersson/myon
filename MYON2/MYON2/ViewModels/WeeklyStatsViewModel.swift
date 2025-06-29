import Foundation

@MainActor
class WeeklyStatsViewModel: ObservableObject {
    @Published var stats: WeeklyStats?
    @Published var recentStats: [WeeklyStats] = []
    @Published var frequencyGoal: Int?
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var hasError = false

    private let analyticsRepository = AnalyticsRepository()
    private let userRepository = UserRepository()
    private let cache = DashboardCache.shared

    func loadDashboard(weekCount: Int = 8, useCache: Bool = true) async {
        guard let userId = AuthService.shared.currentUser?.uid else {
            setError("User not authenticated")
            return
        }

        isLoading = true
        clearError()

        if useCache,
           let cached = cache.load(userId: userId),
           !cache.isExpired(cached) {
            stats = cached.stats
            recentStats = cached.recent
            frequencyGoal = cached.goal
            isLoading = false
            return
        }

        do {
            // Try to load current week first (using user's preference)
            var currentWeekStats = try await analyticsRepository.getCurrentWeekStats(userId: userId)

            if currentWeekStats == nil {
                // If no current week data, try last week
                currentWeekStats = try await analyticsRepository.getLastWeekStats(userId: userId)
            }

            stats = currentWeekStats

            recentStats = try await analyticsRepository.getRecentWeeklyStats(userId: userId, weekCount: weekCount)

            if let attributes = try await userRepository.getUserAttributes(userId: userId) {
                frequencyGoal = attributes.workoutFrequency
            }

            let cached = CachedDashboard(
                stats: stats,
                recent: recentStats,
                goal: frequencyGoal,
                timestamp: Date()
            )
            cache.save(cached, userId: userId)
        } catch {
            setError("Failed to load weekly stats: \(error.localizedDescription)")
        }

        isLoading = false
    }

    func retry() async {
        await loadDashboard(useCache: false)
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

