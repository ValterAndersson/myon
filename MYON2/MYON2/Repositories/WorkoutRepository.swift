import Foundation
import FirebaseFirestore
import OSLog

class WorkoutRepository {
    private let db = Firestore.firestore()
    private let logger = Logger(subsystem: "com.myon.app", category: "WorkoutRepository")
    
    func getWorkouts(userId: String) async throws -> [Workout] {
        do {
            let snapshot = try await db.collection("users").document(userId).collection("workouts").getDocuments()
            return snapshot.documents.compactMap { try? $0.data(as: Workout.self) }
        } catch {
            print("[WorkoutRepository] getWorkouts error for userId \(userId): \(error)")
            throw error
        }
    }
    
    func getWorkout(id: String, userId: String) async throws -> Workout? {
        do {
            let doc = try await db.collection("users").document(userId).collection("workouts").document(id).getDocument()
            return try doc.data(as: Workout.self)
        } catch {
            print("[WorkoutRepository] getWorkout error for id \(id), userId \(userId): \(error)")
            throw error
        }
    }
    
    func createWorkout(userId: String, workout: Workout) async throws -> String {
        return try await retry(times: 3, delay: 0.5) { [self] in
            let ref = try await self.db.collection("users").document(userId).collection("workouts").addDocument(from: workout)
            logger.debug("Workout created for user: \(userId)")
            return ref.documentID
        }
    }
    
    func updateWorkout(userId: String, id: String, workout: Workout) async throws {
        try await retry(times: 3, delay: 0.5) { [self] in
            try await self.db.collection("users").document(userId).collection("workouts").document(id).setData(from: workout, merge: true)
            logger.debug("Workout updated for user: \(userId)")
        }
    }
}
