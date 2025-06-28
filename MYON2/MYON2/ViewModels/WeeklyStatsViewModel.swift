import Foundation

@MainActor
class WeeklyStatsViewModel: ObservableObject {
    @Published var stats: WeeklyStats?
    @Published var isLoading = false
    @Published var error: Error?

    private let repository = AnalyticsRepository()

    func loadCurrentWeek() async {
        guard let userId = AuthService.shared.currentUser?.uid else { return }
        let formatter = DateFormatter()
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        formatter.dateFormat = "yyyy-MM-dd"
        let weekId = formatter.string(from: Calendar.current.startOfWeek(for: Date()))

        isLoading = true
        do {
            stats = try await repository.getWeeklyStats(userId: userId, weekId: weekId)
        } catch {
            self.error = error
        }
        isLoading = false
    }
}

private extension Calendar {
    func startOfWeek(for date: Date) -> Date {
        let components = dateComponents([.yearForWeekOfYear, .weekOfYear], from: date)
        return self.date(from: components) ?? date
    }
}

