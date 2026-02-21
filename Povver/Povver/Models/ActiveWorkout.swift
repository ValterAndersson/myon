import Foundation

struct ActiveWorkout: Codable, Identifiable {
    let id: String
    var userId: String
    var sourceTemplateId: String?
    var createdAt: Date
    var startTime: Date
    var endTime: Date?
    var notes: String?
    var exercises: [ActiveExercise]
}

struct ActiveExercise: Codable, Identifiable, Equatable {
    let id: String // Unique for this workout instance
    var exerciseId: String // Reference to master exercise
    var name: String
    var position: Int // Order in workout
    var sets: [ActiveSet]
}

struct ActiveSet: Codable, Identifiable, Equatable {
    let id: String // Unique for this set
    var reps: Int
    var rir: Int? // nil means not recorded (e.g. warmups)
    var type: String // "Warm-up", "Working Set", etc.
    var weight: Double
    var isCompleted: Bool = false // Track completion state
} 