import Foundation

struct WeeklyStats: Codable, Identifiable {
    let id: String // week id in YYYY-MM-DD format
    let workouts: Int
    let totalSets: Int
    let totalReps: Int
    let totalWeight: Double
    let weightPerMuscleGroup: [String: Double]?
    let weightPerMuscle: [String: Double]?
    let repsPerMuscleGroup: [String: Int]?
    let repsPerMuscle: [String: Int]?
    let setsPerMuscleGroup: [String: Int]?
    let setsPerMuscle: [String: Int]?
    let updatedAt: Date?

    enum CodingKeys: String, CodingKey {
        case id
        case workouts
        case totalSets = "total_sets"
        case totalReps = "total_reps"
        case totalWeight = "total_weight"
        case weightPerMuscleGroup = "weight_per_muscle_group"
        case weightPerMuscle = "weight_per_muscle"
        case repsPerMuscleGroup = "reps_per_muscle_group"
        case repsPerMuscle = "reps_per_muscle"
        case setsPerMuscleGroup = "sets_per_muscle_group"
        case setsPerMuscle = "sets_per_muscle"
        case updatedAt = "updated_at"
    }
}

