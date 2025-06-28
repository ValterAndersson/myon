import Foundation

struct Workout: Codable, Identifiable {
    let id: String
    let userId: String
    var sourceTemplateId: String?
    var createdAt: Date
    var startTime: Date
    var endTime: Date
    var exercises: [WorkoutExercise]
    var notes: String?
    var analytics: WorkoutAnalytics
    
    enum CodingKeys: String, CodingKey {
        case id
        case userId = "user_id"
        case sourceTemplateId = "source_template_id"
        case createdAt = "created_at"
        case startTime = "start_time"
        case endTime = "end_time"
        case exercises
        case notes
        case analytics
    }
}

struct WorkoutExercise: Codable, Identifiable {
    let id: String
    let exerciseId: String
    var name: String
    var position: Int
    var sets: [WorkoutExerciseSet]
    var analytics: ExerciseAnalytics
    
    enum CodingKeys: String, CodingKey {
        case id
        case exerciseId = "exercise_id"
        case name
        case position
        case sets
        case analytics
    }
}

struct WorkoutExerciseSet: Codable, Identifiable {
    let id: String
    var reps: Int
    var rir: Int // Reps in Reserve
    var type: String // "Warm-up", "Working Set", etc.
    var weight: Double // Changed to match Firestore weight_kg
    var isCompleted: Bool // Track completion state
    
    enum CodingKeys: String, CodingKey {
        case id
        case reps
        case rir
        case type
        case weight = "weight_kg"
        case isCompleted = "is_completed"
    }
}

struct ExerciseAnalytics: Codable {
    let totalSets: Int
    let totalReps: Int
    let totalWeight: Double
    let weightFormat: String // "kg" or "lbs"
    let avgRepsPerSet: Double
    let avgWeightPerSet: Double
    let avgWeightPerRep: Double
    let weightPerMuscleGroup: [String: Double]
    let weightPerMuscle: [String: Double]
    let repsPerMuscleGroup: [String: Double]
    let repsPerMuscle: [String: Double]
    let setsPerMuscleGroup: [String: Int]
    let setsPerMuscle: [String: Int]
    
    enum CodingKeys: String, CodingKey {
        case totalSets = "total_sets"
        case totalReps = "total_reps"
        case totalWeight = "total_weight"
        case weightFormat = "weight_format"
        case avgRepsPerSet = "avg_reps_per_set"
        case avgWeightPerSet = "avg_weight_per_set"
        case avgWeightPerRep = "avg_weight_per_rep"
        case weightPerMuscleGroup = "weight_per_muscle_group"
        case weightPerMuscle = "weight_per_muscle"
        case repsPerMuscleGroup = "reps_per_muscle_group"
        case repsPerMuscle = "reps_per_muscle"
        case setsPerMuscleGroup = "sets_per_muscle_group"
        case setsPerMuscle = "sets_per_muscle"
    }
}

struct WorkoutAnalytics: Codable {
    let totalSets: Int
    let totalReps: Int
    let totalWeight: Double
    let weightFormat: String // "kg" or "lbs"
    let avgRepsPerSet: Double
    let avgWeightPerSet: Double
    let avgWeightPerRep: Double
    let weightPerMuscleGroup: [String: Double]
    let weightPerMuscle: [String: Double]
    let repsPerMuscleGroup: [String: Double]
    let repsPerMuscle: [String: Double]
    let setsPerMuscleGroup: [String: Int]
    let setsPerMuscle: [String: Int]
    
    enum CodingKeys: String, CodingKey {
        case totalSets = "total_sets"
        case totalReps = "total_reps"
        case totalWeight = "total_weight"
        case weightFormat = "weight_format"
        case avgRepsPerSet = "avg_reps_per_set"
        case avgWeightPerSet = "avg_weight_per_set"
        case avgWeightPerRep = "avg_weight_per_rep"
        case weightPerMuscleGroup = "weight_per_muscle_group"
        case weightPerMuscle = "weight_per_muscle"
        case repsPerMuscleGroup = "reps_per_muscle_group"
        case repsPerMuscle = "reps_per_muscle"
        case setsPerMuscleGroup = "sets_per_muscle_group"
        case setsPerMuscle = "sets_per_muscle"
    }
} 