import Foundation
import FirebaseFirestore

/// Pre-computed exercise usage statistics for sorting exercises by recency and frequency.
/// Written by Firebase triggers on workout completion; read-only from the client.
/// Path: users/{uid}/exercise_usage_stats/{exerciseId}
struct ExerciseUsageStats: Codable, Identifiable {
    @DocumentID var id: String?
    let exerciseId: String
    let exerciseName: String
    let lastWorkoutDate: String?     // "YYYY-MM-DD"
    let workoutCount: Int

    enum CodingKeys: String, CodingKey {
        case id
        case exerciseId = "exercise_id"
        case exerciseName = "exercise_name"
        case lastWorkoutDate = "last_workout_date"
        case workoutCount = "workout_count"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        _id = try container.decode(DocumentID<String>.self, forKey: .id)
        exerciseId = try container.decode(String.self, forKey: .exerciseId)
        exerciseName = try container.decodeIfPresent(String.self, forKey: .exerciseName) ?? ""
        lastWorkoutDate = try container.decodeIfPresent(String.self, forKey: .lastWorkoutDate)
        workoutCount = try container.decodeIfPresent(Int.self, forKey: .workoutCount) ?? 0
    }
}
