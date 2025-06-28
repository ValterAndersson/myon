import Foundation
import FirebaseFirestore

class AnalyticsRepository {
    private let db = Firestore.firestore()

    func getWeeklyStats(userId: String, weekId: String) async throws -> WeeklyStats? {
        let doc = try await db.collection("users").document(userId)
            .collection("analytics").collection("weekly_stats")
            .document(weekId).getDocument()
        return try doc.data(as: WeeklyStats.self)
    }
}

