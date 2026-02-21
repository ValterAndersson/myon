import Foundation

// MARK: - Firestore Timestamp DTO

/// Firestore timestamp format: { _seconds: Int, _nanoseconds: Int }
struct FirestoreTimestampDTO: Decodable {
    let seconds: Int
    let nanoseconds: Int
    
    enum CodingKeys: String, CodingKey {
        case seconds = "_seconds"
        case nanoseconds = "_nanoseconds"
    }
    
    var date: Date {
        let timeInterval = TimeInterval(seconds) + TimeInterval(nanoseconds) / 1_000_000_000
        return Date(timeIntervalSince1970: timeInterval)
    }
}

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
    
    // Lenient decoder - all fields optional with sensible defaults
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.totalSets = try container.decodeIfPresent(Int.self, forKey: .totalSets) ?? 0
        self.totalReps = try container.decodeIfPresent(Int.self, forKey: .totalReps) ?? 0
        self.projectedVolume = try container.decodeIfPresent(Double.self, forKey: .projectedVolume) ?? 0
        self.projectedVolumePerMuscleGroup = try container.decodeIfPresent([String: Double].self, forKey: .projectedVolumePerMuscleGroup) ?? [:]
        self.estimatedDuration = try container.decodeIfPresent(Int.self, forKey: .estimatedDuration) ?? 0
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
    
    // Memberwise init for backward compatibility
    init(id: String, userId: String, name: String, description: String? = nil,
         exercises: [WorkoutTemplateExercise], analytics: TemplateAnalytics? = nil,
         createdAt: Date, updatedAt: Date) {
        self.id = id
        self.userId = userId
        self.name = name
        self.description = description
        self.exercises = exercises
        self.analytics = analytics
        self.createdAt = createdAt
        self.updatedAt = updatedAt
    }
    
    // Lenient decoder for API responses
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.id = try container.decodeIfPresent(String.self, forKey: .id) ?? UUID().uuidString
        self.userId = try container.decodeIfPresent(String.self, forKey: .userId) ?? ""
        self.name = try container.decodeIfPresent(String.self, forKey: .name) ?? "Untitled"
        self.description = try container.decodeIfPresent(String.self, forKey: .description)
        self.exercises = try container.decodeIfPresent([WorkoutTemplateExercise].self, forKey: .exercises) ?? []
        self.analytics = try container.decodeIfPresent(TemplateAnalytics.self, forKey: .analytics)
        
        // Handle created_at as either Date, ISO string, or Firestore timestamp dict
        self.createdAt = Self.decodeFlexibleDate(from: container, key: .createdAt) ?? Date()
        self.updatedAt = Self.decodeFlexibleDate(from: container, key: .updatedAt) ?? Date()
    }
    
    /// Decode date from various formats: Date, ISO8601 string, or Firestore timestamp dictionary
    private static func decodeFlexibleDate(from container: KeyedDecodingContainer<CodingKeys>, key: CodingKeys) -> Date? {
        // Try as Date first (default Codable)
        if let date = try? container.decode(Date.self, forKey: key) {
            return date
        }
        
        // Try as ISO8601 string
        if let string = try? container.decode(String.self, forKey: key) {
            let iso8601 = ISO8601DateFormatter()
            iso8601.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            if let date = iso8601.date(from: string) {
                return date
            }
            iso8601.formatOptions = [.withInternetDateTime]
            if let date = iso8601.date(from: string) {
                return date
            }
        }
        
        // Try as Firestore timestamp dictionary { _seconds: Int, _nanoseconds: Int }
        if let firestoreTimestamp = try? container.decode(FirestoreTimestampDTO.self, forKey: key) {
            return firestoreTimestamp.date
        }
        
        return nil
    }
}

struct WorkoutTemplateExercise: Codable, Identifiable, Equatable {
    let id: String // Unique for this template exercise
    var exerciseId: String // Reference to master exercise
    var name: String? // Exercise name (optional for display)
    var position: Int
    var sets: [WorkoutTemplateSet]
    var restBetweenSets: Int?
    
    enum CodingKeys: String, CodingKey {
        case id
        case exerciseId = "exercise_id"
        case name
        case position
        case sets
        case restBetweenSets = "rest_between_sets"
    }
    
    // Memberwise init for backward compatibility
    init(id: String, exerciseId: String, name: String? = nil, position: Int,
         sets: [WorkoutTemplateSet], restBetweenSets: Int? = nil) {
        self.id = id
        self.exerciseId = exerciseId
        self.name = name
        self.position = position
        self.sets = sets
        self.restBetweenSets = restBetweenSets
    }
    
    // Lenient decoder for API responses
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.id = try container.decodeIfPresent(String.self, forKey: .id) ?? UUID().uuidString
        self.exerciseId = try container.decodeIfPresent(String.self, forKey: .exerciseId) ?? ""
        self.name = try container.decodeIfPresent(String.self, forKey: .name)
        self.position = try container.decodeIfPresent(Int.self, forKey: .position) ?? 0
        self.sets = try container.decodeIfPresent([WorkoutTemplateSet].self, forKey: .sets) ?? []
        self.restBetweenSets = try container.decodeIfPresent(Int.self, forKey: .restBetweenSets)
    }
}

struct WorkoutTemplateSet: Codable, Identifiable, Equatable {
    let id: String // Unique for this set
    var reps: Int
    var rir: Int? // nil means not recorded (e.g. warmups)
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

    // Memberwise init for backward compatibility
    init(id: String, reps: Int, rir: Int?, type: String, weight: Double, duration: Int? = nil) {
        self.id = id
        self.reps = reps
        self.rir = rir
        self.type = type
        self.weight = weight
        self.duration = duration
    }

    // Lenient decoder for API responses
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.id = try container.decodeIfPresent(String.self, forKey: .id) ?? UUID().uuidString
        self.reps = try container.decodeIfPresent(Int.self, forKey: .reps) ?? 0
        self.rir = try container.decodeIfPresent(Int.self, forKey: .rir)
        self.type = try container.decodeIfPresent(String.self, forKey: .type) ?? "working"
        self.weight = try container.decodeIfPresent(Double.self, forKey: .weight) ?? 0
        self.duration = try container.decodeIfPresent(Int.self, forKey: .duration)
    }
}
