import Foundation

@MainActor
class WeeklyStatsViewModel: ObservableObject {
    @Published var stats: WeeklyStats?
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var hasError = false

    private let repository = AnalyticsRepository()

    func loadCurrentWeek() async {
        guard let userId = AuthService.shared.currentUser?.uid else { 
            setError("User not authenticated")
            return 
        }

        isLoading = true
        clearError()
        
        do {
            // Try to load current week first (using user's preference)
            var currentWeekStats = try await repository.getCurrentWeekStats(userId: userId)
            
            if currentWeekStats == nil {
                // If no current week data, try last week
                currentWeekStats = try await repository.getLastWeekStats(userId: userId)
            }
            
            stats = currentWeekStats
        } catch {
            setError("Failed to load weekly stats: \(error.localizedDescription)")
        }
        
        isLoading = false
    }
    
    func retry() async {
        await loadCurrentWeek()
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

