import Foundation
import FirebaseFirestore

enum AnalyticsError: Error, LocalizedError {
    case userNotFound
    case weeklyStatsNotFound
    case invalidWeekId
    case firestoreError(Error)
    
    var errorDescription: String? {
        switch self {
        case .userNotFound:
            return "User not found"
        case .weeklyStatsNotFound:
            return "Weekly stats not found for this period"
        case .invalidWeekId:
            return "Invalid week ID format"
        case .firestoreError(let error):
            return "Database error: \(error.localizedDescription)"
        }
    }
}

class AnalyticsRepository {
    private let db = Firestore.firestore()
    
    // MARK: - Weekly Stats
    
    /// Get weekly stats for a specific user and week
    func getWeeklyStats(userId: String, weekId: String) async throws -> WeeklyStats? {
        guard isValidWeekId(weekId) else {
            throw AnalyticsError.invalidWeekId
        }
        
        do {
            let doc = try await db.collection("users").document(userId)
                .collection("analytics")
                .collection("weekly_stats")
                .document(weekId).getDocument()
            
            if !doc.exists {
                return nil
            }
            
            return try doc.data(as: WeeklyStats.self)
        } catch {
            throw AnalyticsError.firestoreError(error)
        }
    }
    
    /// Get current week's stats for a user
    func getCurrentWeekStats(userId: String) async throws -> WeeklyStats? {
        let currentWeekId = getCurrentWeekId()
        return try await getWeeklyStats(userId: userId, weekId: currentWeekId)
    }
    
    /// Get last week's stats for a user
    func getLastWeekStats(userId: String) async throws -> WeeklyStats? {
        let lastWeekId = getLastWeekId()
        return try await getWeeklyStats(userId: userId, weekId: lastWeekId)
    }
    
    /// Get multiple weeks of stats for a user
    func getWeeklyStatsRange(userId: String, startWeekId: String, endWeekId: String) async throws -> [WeeklyStats] {
        guard isValidWeekId(startWeekId), isValidWeekId(endWeekId) else {
            throw AnalyticsError.invalidWeekId
        }
        
        do {
            let query = db.collection("users").document(userId)
                .collection("analytics")
                .collection("weekly_stats")
                .whereField(FieldPath.documentID(), isGreaterThanOrEqualTo: startWeekId)
                .whereField(FieldPath.documentID(), isLessThanOrEqualTo: endWeekId)
                .order(by: FieldPath.documentID(), descending: true)
            
            let snapshot = try await query.getDocuments()
            return try snapshot.documents.compactMap { doc in
                try doc.data(as: WeeklyStats.self)
            }
        } catch {
            throw AnalyticsError.firestoreError(error)
        }
    }
    
    /// Get the last N weeks of stats for a user
    func getRecentWeeklyStats(userId: String, weekCount: Int = 4) async throws -> [WeeklyStats] {
        let endWeekId = getCurrentWeekId()
        let startWeekId = getWeekId(weeksAgo: weekCount - 1)
        
        return try await getWeeklyStatsRange(userId: userId, startWeekId: startWeekId, endWeekId: endWeekId)
    }
    
    /// Check if weekly stats exist for a specific week
    func weeklyStatsExist(userId: String, weekId: String) async throws -> Bool {
        let stats = try await getWeeklyStats(userId: userId, weekId: weekId)
        return stats != nil
    }
    
    // MARK: - Helper Methods
    
    /// Get current week ID in YYYY-MM-DD format (Sunday start)
    private func getCurrentWeekId() -> String {
        return getWeekId(weeksAgo: 0)
    }
    
    /// Get last week ID in YYYY-MM-DD format (Sunday start)
    private func getLastWeekId() -> String {
        return getWeekId(weeksAgo: 1)
    }
    
    /// Get week ID for N weeks ago (Sunday start to match Firebase function)
    private func getWeekId(weeksAgo: Int) -> String {
        let now = Date()
        let calendar = Calendar.current
        
        // Ensure Sunday start (matching Firebase function)
        var adjustedCalendar = calendar
        adjustedCalendar.firstWeekday = 1 // Sunday = 1
        
        let weekDate = adjustedCalendar.date(byAdding: .weekOfYear, value: -weeksAgo, to: now) ?? now
        let startOfWeek = adjustedCalendar.startOfWeek(for: weekDate)
        
        let formatter = DateFormatter()
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        formatter.dateFormat = "yyyy-MM-dd"
        
        return formatter.string(from: startOfWeek)
    }
    
    /// Validate week ID format (YYYY-MM-DD)
    private func isValidWeekId(_ weekId: String) -> Bool {
        let pattern = #"^\d{4}-\d{2}-\d{2}$"#
        let regex = try? NSRegularExpression(pattern: pattern)
        let range = NSRange(location: 0, length: weekId.utf16.count)
        return regex?.firstMatch(in: weekId, options: [], range: range) != nil
    }
}

// MARK: - Calendar Extension

private extension Calendar {
    func startOfWeek(for date: Date) -> Date {
        let components = dateComponents([.yearForWeekOfYear, .weekOfYear], from: date)
        return self.date(from: components) ?? date
    }
}

