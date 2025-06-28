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
        
        let formatter = DateFormatter()
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        formatter.dateFormat = "yyyy-MM-dd"
        let weekId = formatter.string(from: Calendar.current.startOfWeek(for: Date()))

        isLoading = true
        clearError()
        
        do {
            stats = try await repository.getWeeklyStats(userId: userId, weekId: weekId)
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

private extension Calendar {
    func startOfWeek(for date: Date) -> Date {
        // Use Sunday as the start of the week to match Firebase function
        var calendar = Calendar.current
        calendar.firstWeekday = 1 // Sunday = 1
        let components = calendar.dateComponents([.yearForWeekOfYear, .weekOfYear], from: date)
        return calendar.date(from: components) ?? date
    }
}

