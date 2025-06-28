import Foundation

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