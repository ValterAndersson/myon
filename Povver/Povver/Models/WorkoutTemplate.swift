import Foundation

// MARK: - Template Analytics

struct TemplateAnalytics: Codable, Equatable {
    var totalSets: Int
    var totalReps: Int
    var projectedVolume: Double
    var projectedVolumePerMuscleGroup: [String: Double]
    var estimatedDuration: Int // in minutes
    
    init(totalSets: Int = 0, totalReps: Int = 0, projectedVolume: Double = 0, projectedVolumePerMuscleGroup: [String: Double] = [:], estimatedDuration: Int = 0) {
        self.totalSets = totalSets
        self.totalReps = totalReps
        self.projectedVolume = projectedVolume
        self.projectedVolumePerMuscleGroup = projectedVolumePerMuscleGroup
        self.estimatedDuration = estimatedDuration
    }
    
    enum CodingKeys: String, CodingKey {
        case totalSets = "total_sets"
        case totalReps = "total_reps"
        case projectedVolume = "projected_volume"
        case projectedVolumePerMuscleGroup = "projected_volume_per_muscle_group"
        case estimatedDuration = "estimated_duration"
    }
}

// MARK: - Workout Template

struct WorkoutTemplate: Codable, Identifiable, Equatable {
    let id: String
    let userId: String
    var name: String
    var description: String?
    var exercises: [WorkoutTemplateExercise]
    var analytics: TemplateAnalytics? // Computed analytics saved with template
    var createdAt: Date
    var updatedAt: Date
    
    enum CodingKeys: String, CodingKey {
        case id
        case userId = "user_id"
        case name
        case description
        case exercises
        case analytics
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }
}

struct WorkoutTemplateExercise: Codable, Identifiable, Equatable {
    let id: String // Unique for this template exercise
    var exerciseId: String // Reference to master exercise
    var position: Int
    var sets: [WorkoutTemplateSet]
    var restBetweenSets: Int?
    
    enum CodingKeys: String, CodingKey {
        case id
        case exerciseId = "exercise_id"
        case position
        case sets
        case restBetweenSets = "rest_between_sets"
    }
}

struct WorkoutTemplateSet: Codable, Identifiable, Equatable {
    let id: String // Unique for this set
    var reps: Int
    var rir: Int
    var type: String
    var weight: Double
    var duration: Int?
    
    enum CodingKeys: String, CodingKey {
        case id
        case reps
        case rir
        case type
        case weight
        case duration
    }
}
