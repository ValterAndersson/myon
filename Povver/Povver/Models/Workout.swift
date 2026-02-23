import Foundation

struct Workout: Codable, Identifiable {
    var id: String
    let userId: String
    var name: String?  // Workout name (set by user or from template)
    var sourceTemplateId: String?
    var createdAt: Date
    var startTime: Date
    var endTime: Date
    var exercises: [WorkoutExercise]
    var notes: String?
    var analytics: WorkoutAnalytics
    var templateDiff: WorkoutTemplateDiff?

    enum CodingKeys: String, CodingKey {
        case id
        case userId = "user_id"
        case name
        case sourceTemplateId = "source_template_id"
        case createdAt = "created_at"
        case startTime = "start_time"
        case endTime = "end_time"
        case exercises
        case notes
        case analytics
        case templateDiff = "template_diff"
    }
    
    // Memberwise init for backward compatibility
    init(id: String, userId: String, name: String? = nil, sourceTemplateId: String? = nil, createdAt: Date,
         startTime: Date, endTime: Date, exercises: [WorkoutExercise], notes: String? = nil,
         analytics: WorkoutAnalytics, templateDiff: WorkoutTemplateDiff? = nil) {
        self.id = id
        self.userId = userId
        self.name = name
        self.sourceTemplateId = sourceTemplateId
        self.createdAt = createdAt
        self.startTime = startTime
        self.endTime = endTime
        self.exercises = exercises
        self.notes = notes
        self.analytics = analytics
        self.templateDiff = templateDiff
    }
    
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        
        // Use document ID as fallback if 'id' field is missing
        if let id = try container.decodeIfPresent(String.self, forKey: .id) {
            self.id = id
        } else if let docId = decoder.userInfo[.documentID] as? String {
            self.id = docId
        } else {
            self.id = UUID().uuidString
        }
        
        self.userId = try container.decodeIfPresent(String.self, forKey: .userId) ?? ""
        self.name = try container.decodeIfPresent(String.self, forKey: .name)
        self.sourceTemplateId = try container.decodeIfPresent(String.self, forKey: .sourceTemplateId)
        self.createdAt = try container.decodeIfPresent(Date.self, forKey: .createdAt) ?? Date()
        self.startTime = try container.decodeIfPresent(Date.self, forKey: .startTime) ?? Date()
        self.endTime = try container.decodeIfPresent(Date.self, forKey: .endTime) ?? Date()
        self.exercises = try container.decodeIfPresent([WorkoutExercise].self, forKey: .exercises) ?? []
        self.notes = try container.decodeIfPresent(String.self, forKey: .notes)
        self.analytics = try container.decodeIfPresent(WorkoutAnalytics.self, forKey: .analytics) ?? WorkoutAnalytics.empty
        self.templateDiff = try container.decodeIfPresent(WorkoutTemplateDiff.self, forKey: .templateDiff)
    }
    
    /// Generate a display name for UI with proper priority:
    /// 1. Use name if set (app-created workouts)
    /// 2. For imported workouts (id starts with "imp"), use notes
    /// 3. Fall back to first exercise + N more pattern
    var displayName: String {
        // Priority 1: Use name if set
        if let name = name, !name.isEmpty {
            return name
        }
        
        // Priority 2: For imported workouts, use notes field
        if id.hasPrefix("imp"), let notes = notes, !notes.isEmpty {
            return notes
        }
        
        // Priority 3: Fall back to first exercise + N more
        if let firstExercise = exercises.first {
            let count = exercises.count
            return count > 1 ? "\(firstExercise.name) + \(count - 1) more" : firstExercise.name
        }
        
        return "Workout"
    }
}

extension CodingUserInfoKey {
    static let documentID = CodingUserInfoKey(rawValue: "documentID")!
}

struct WorkoutExercise: Codable, Identifiable {
    let id: String
    let exerciseId: String
    var name: String
    var position: Int
    var sets: [WorkoutExerciseSet]
    var notes: String?
    var analytics: ExerciseAnalytics

    enum CodingKeys: String, CodingKey {
        case id
        case exerciseId = "exercise_id"
        case name
        case position
        case sets
        case notes
        case analytics
    }

    // Memberwise init for backward compatibility
    init(id: String, exerciseId: String, name: String, position: Int, sets: [WorkoutExerciseSet], notes: String? = nil, analytics: ExerciseAnalytics) {
        self.id = id
        self.exerciseId = exerciseId
        self.name = name
        self.position = position
        self.sets = sets
        self.notes = notes
        self.analytics = analytics
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.id = try container.decodeIfPresent(String.self, forKey: .id) ?? UUID().uuidString
        self.exerciseId = try container.decodeIfPresent(String.self, forKey: .exerciseId) ?? ""
        self.name = try container.decodeIfPresent(String.self, forKey: .name) ?? "Unknown"
        self.position = try container.decodeIfPresent(Int.self, forKey: .position) ?? 0
        self.sets = try container.decodeIfPresent([WorkoutExerciseSet].self, forKey: .sets) ?? []
        self.notes = try container.decodeIfPresent(String.self, forKey: .notes)
        self.analytics = try container.decodeIfPresent(ExerciseAnalytics.self, forKey: .analytics) ?? ExerciseAnalytics.empty
    }
}

struct WorkoutExerciseSet: Codable, Identifiable {
    let id: String
    var reps: Int
    var rir: Int? // Reps in Reserve — nil means not recorded (e.g. warmups)
    var type: String // "warmup", "working", "dropset", etc.
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

    // Memberwise init for backward compatibility
    init(id: String, reps: Int, rir: Int?, type: String, weight: Double, isCompleted: Bool) {
        self.id = id
        self.reps = reps
        self.rir = rir
        self.type = type
        self.weight = weight
        self.isCompleted = isCompleted
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.id = try container.decodeIfPresent(String.self, forKey: .id) ?? UUID().uuidString
        self.reps = try container.decodeIfPresent(Int.self, forKey: .reps) ?? 0
        self.rir = try container.decodeIfPresent(Int.self, forKey: .rir)
        self.type = try container.decodeIfPresent(String.self, forKey: .type) ?? "working"  // Match backend format
        self.weight = try container.decodeIfPresent(Double.self, forKey: .weight) ?? 0
        self.isCompleted = try container.decodeIfPresent(Bool.self, forKey: .isCompleted) ?? true
    }
}

/// Intensity metrics computed by analytics-calculator.js — stimulus sets, effort distribution, estimated 1RM.
/// All fields optional with nil defaults for backward compatibility with older workout docs.
struct IntensityAnalytics: Codable {
    let hardSets: Int
    let lowRirSets: Int
    let avgRelativeIntensity: Double
    let loadPerMuscle: [String: Double]
    let hardSetsPerMuscle: [String: Double]
    let lowRirSetsPerMuscle: [String: Double]
    let topSetE1rmPerMuscle: [String: Double]
    let loadPerMuscleGroup: [String: Double]
    let hardSetsPerMuscleGroup: [String: Double]
    let lowRirSetsPerMuscleGroup: [String: Double]

    static let empty = IntensityAnalytics(
        hardSets: 0, lowRirSets: 0, avgRelativeIntensity: 0,
        loadPerMuscle: [:], hardSetsPerMuscle: [:], lowRirSetsPerMuscle: [:],
        topSetE1rmPerMuscle: [:],
        loadPerMuscleGroup: [:], hardSetsPerMuscleGroup: [:], lowRirSetsPerMuscleGroup: [:]
    )

    enum CodingKeys: String, CodingKey {
        case hardSets = "hard_sets"
        case lowRirSets = "low_rir_sets"
        case avgRelativeIntensity = "avg_relative_intensity"
        case loadPerMuscle = "load_per_muscle"
        case hardSetsPerMuscle = "hard_sets_per_muscle"
        case lowRirSetsPerMuscle = "low_rir_sets_per_muscle"
        case topSetE1rmPerMuscle = "top_set_e1rm_per_muscle"
        case loadPerMuscleGroup = "load_per_muscle_group"
        case hardSetsPerMuscleGroup = "hard_sets_per_muscle_group"
        case lowRirSetsPerMuscleGroup = "low_rir_sets_per_muscle_group"
    }

    init(hardSets: Int, lowRirSets: Int, avgRelativeIntensity: Double,
         loadPerMuscle: [String: Double], hardSetsPerMuscle: [String: Double],
         lowRirSetsPerMuscle: [String: Double], topSetE1rmPerMuscle: [String: Double],
         loadPerMuscleGroup: [String: Double], hardSetsPerMuscleGroup: [String: Double],
         lowRirSetsPerMuscleGroup: [String: Double]) {
        self.hardSets = hardSets
        self.lowRirSets = lowRirSets
        self.avgRelativeIntensity = avgRelativeIntensity
        self.loadPerMuscle = loadPerMuscle
        self.hardSetsPerMuscle = hardSetsPerMuscle
        self.lowRirSetsPerMuscle = lowRirSetsPerMuscle
        self.topSetE1rmPerMuscle = topSetE1rmPerMuscle
        self.loadPerMuscleGroup = loadPerMuscleGroup
        self.hardSetsPerMuscleGroup = hardSetsPerMuscleGroup
        self.lowRirSetsPerMuscleGroup = lowRirSetsPerMuscleGroup
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.hardSets = try container.decodeIfPresent(Int.self, forKey: .hardSets) ?? 0
        self.lowRirSets = try container.decodeIfPresent(Int.self, forKey: .lowRirSets) ?? 0
        self.avgRelativeIntensity = try container.decodeIfPresent(Double.self, forKey: .avgRelativeIntensity) ?? 0
        self.loadPerMuscle = try container.decodeIfPresent([String: Double].self, forKey: .loadPerMuscle) ?? [:]
        self.hardSetsPerMuscle = try container.decodeIfPresent([String: Double].self, forKey: .hardSetsPerMuscle) ?? [:]
        self.lowRirSetsPerMuscle = try container.decodeIfPresent([String: Double].self, forKey: .lowRirSetsPerMuscle) ?? [:]
        self.topSetE1rmPerMuscle = try container.decodeIfPresent([String: Double].self, forKey: .topSetE1rmPerMuscle) ?? [:]
        self.loadPerMuscleGroup = try container.decodeIfPresent([String: Double].self, forKey: .loadPerMuscleGroup) ?? [:]
        self.hardSetsPerMuscleGroup = try container.decodeIfPresent([String: Double].self, forKey: .hardSetsPerMuscleGroup) ?? [:]
        self.lowRirSetsPerMuscleGroup = try container.decodeIfPresent([String: Double].self, forKey: .lowRirSetsPerMuscleGroup) ?? [:]
    }
}

struct ExerciseAnalytics: Codable {
    let totalSets: Int
    let totalReps: Int
    let totalWeight: Double
    let weightFormat: String
    let avgRepsPerSet: Double
    let avgWeightPerSet: Double
    let avgWeightPerRep: Double
    let weightPerMuscleGroup: [String: Double]
    let weightPerMuscle: [String: Double]
    let repsPerMuscleGroup: [String: Double]
    let repsPerMuscle: [String: Double]
    let setsPerMuscleGroup: [String: Int]
    let setsPerMuscle: [String: Int]
    let intensity: IntensityAnalytics?

    static let empty = ExerciseAnalytics(
        totalSets: 0, totalReps: 0, totalWeight: 0, weightFormat: "kg",
        avgRepsPerSet: 0, avgWeightPerSet: 0, avgWeightPerRep: 0,
        weightPerMuscleGroup: [:], weightPerMuscle: [:],
        repsPerMuscleGroup: [:], repsPerMuscle: [:],
        setsPerMuscleGroup: [:], setsPerMuscle: [:],
        intensity: nil
    )

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
        case intensity
    }

    init(totalSets: Int, totalReps: Int, totalWeight: Double, weightFormat: String,
         avgRepsPerSet: Double, avgWeightPerSet: Double, avgWeightPerRep: Double,
         weightPerMuscleGroup: [String: Double], weightPerMuscle: [String: Double],
         repsPerMuscleGroup: [String: Double], repsPerMuscle: [String: Double],
         setsPerMuscleGroup: [String: Int], setsPerMuscle: [String: Int],
         intensity: IntensityAnalytics? = nil) {
        self.totalSets = totalSets
        self.totalReps = totalReps
        self.totalWeight = totalWeight
        self.weightFormat = weightFormat
        self.avgRepsPerSet = avgRepsPerSet
        self.avgWeightPerSet = avgWeightPerSet
        self.avgWeightPerRep = avgWeightPerRep
        self.weightPerMuscleGroup = weightPerMuscleGroup
        self.weightPerMuscle = weightPerMuscle
        self.repsPerMuscleGroup = repsPerMuscleGroup
        self.repsPerMuscle = repsPerMuscle
        self.setsPerMuscleGroup = setsPerMuscleGroup
        self.setsPerMuscle = setsPerMuscle
        self.intensity = intensity
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.totalSets = try container.decodeIfPresent(Int.self, forKey: .totalSets) ?? 0
        self.totalReps = try container.decodeIfPresent(Int.self, forKey: .totalReps) ?? 0
        self.totalWeight = try container.decodeIfPresent(Double.self, forKey: .totalWeight) ?? 0
        self.weightFormat = try container.decodeIfPresent(String.self, forKey: .weightFormat) ?? "kg"
        self.avgRepsPerSet = try container.decodeIfPresent(Double.self, forKey: .avgRepsPerSet) ?? 0
        self.avgWeightPerSet = try container.decodeIfPresent(Double.self, forKey: .avgWeightPerSet) ?? 0
        self.avgWeightPerRep = try container.decodeIfPresent(Double.self, forKey: .avgWeightPerRep) ?? 0
        self.weightPerMuscleGroup = try container.decodeIfPresent([String: Double].self, forKey: .weightPerMuscleGroup) ?? [:]
        self.weightPerMuscle = try container.decodeIfPresent([String: Double].self, forKey: .weightPerMuscle) ?? [:]
        self.repsPerMuscleGroup = try container.decodeIfPresent([String: Double].self, forKey: .repsPerMuscleGroup) ?? [:]
        self.repsPerMuscle = try container.decodeIfPresent([String: Double].self, forKey: .repsPerMuscle) ?? [:]
        self.setsPerMuscleGroup = try container.decodeIfPresent([String: Int].self, forKey: .setsPerMuscleGroup) ?? [:]
        self.setsPerMuscle = try container.decodeIfPresent([String: Int].self, forKey: .setsPerMuscle) ?? [:]
        self.intensity = try container.decodeIfPresent(IntensityAnalytics.self, forKey: .intensity)
    }
}

// MARK: - Template Diff

/// Structured diff between what the template prescribed and what the user did
struct WorkoutTemplateDiff: Codable {
    var changesDetected: Bool
    var exercisesAdded: [DiffExercise]?
    var exercisesRemoved: [DiffExercise]?
    var exercisesSwapped: [DiffSwap]?
    var exercisesReordered: Bool?
    var weightChanges: [DiffWeightChange]?
    var repChanges: [DiffRepChange]?
    var setsAddedCount: Int?
    var setsRemovedCount: Int?
    var summary: String?

    enum CodingKeys: String, CodingKey {
        case changesDetected = "changes_detected"
        case exercisesAdded = "exercises_added"
        case exercisesRemoved = "exercises_removed"
        case exercisesSwapped = "exercises_swapped"
        case exercisesReordered = "exercises_reordered"
        case weightChanges = "weight_changes"
        case repChanges = "rep_changes"
        case setsAddedCount = "sets_added_count"
        case setsRemovedCount = "sets_removed_count"
        case summary
    }

    struct DiffExercise: Codable {
        let exerciseId: String
        let exerciseName: String

        enum CodingKeys: String, CodingKey {
            case exerciseId = "exercise_id"
            case exerciseName = "exercise_name"
        }
    }

    struct DiffSwap: Codable {
        let fromId: String
        let fromName: String
        let toId: String
        let toName: String

        enum CodingKeys: String, CodingKey {
            case fromId = "from_id"
            case fromName = "from_name"
            case toId = "to_id"
            case toName = "to_name"
        }
    }

    struct DiffWeightChange: Codable {
        let exerciseId: String
        let exerciseName: String
        let direction: String
        let maxDeltaKg: Double

        enum CodingKeys: String, CodingKey {
            case exerciseId = "exercise_id"
            case exerciseName = "exercise_name"
            case direction
            case maxDeltaKg = "max_delta_kg"
        }
    }

    struct DiffRepChange: Codable {
        let exerciseId: String
        let exerciseName: String
        let direction: String
        let maxDelta: Int

        enum CodingKeys: String, CodingKey {
            case exerciseId = "exercise_id"
            case exerciseName = "exercise_name"
            case direction
            case maxDelta = "max_delta"
        }
    }
}

// MARK: - Upsert Workout Request (for editing completed workouts)

/// Request model for the upsertWorkout endpoint.
/// Backend recomputes all analytics, set_facts, and series inline.
struct UpsertWorkoutRequest: Encodable {
    let id: String
    let name: String?
    let startTime: Date
    let endTime: Date
    let exercises: [UpsertExercise]
    let sourceTemplateId: String?
    let notes: String?

    enum CodingKeys: String, CodingKey {
        case id, name
        case startTime = "start_time"
        case endTime = "end_time"
        case exercises
        case sourceTemplateId = "source_template_id"
        case notes
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(id, forKey: .id)
        try container.encodeIfPresent(name, forKey: .name)

        // Encode dates as ISO8601 strings (backend expects string format)
        let isoFormatter = ISO8601DateFormatter()
        isoFormatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        try container.encode(isoFormatter.string(from: startTime), forKey: .startTime)
        try container.encode(isoFormatter.string(from: endTime), forKey: .endTime)

        try container.encode(exercises, forKey: .exercises)
        try container.encodeIfPresent(sourceTemplateId, forKey: .sourceTemplateId)
        try container.encodeIfPresent(notes, forKey: .notes)
    }
}

struct UpsertExercise: Encodable {
    let exerciseId: String
    let name: String
    let position: Int
    let sets: [UpsertSet]

    enum CodingKeys: String, CodingKey {
        case exerciseId = "exercise_id"
        case name, position, sets
    }
}

struct UpsertSet: Encodable {
    let id: String
    let reps: Int
    let rir: Int?
    let type: String
    let weightKg: Double
    let isCompleted: Bool

    enum CodingKeys: String, CodingKey {
        case id, reps, rir, type
        case weightKg = "weight_kg"
        case isCompleted = "is_completed"
    }
}

// MARK: - Workout Analytics

struct WorkoutAnalytics: Codable {
    let totalSets: Int
    let totalReps: Int
    let totalWeight: Double
    let weightFormat: String
    let avgRepsPerSet: Double
    let avgWeightPerSet: Double
    let avgWeightPerRep: Double
    let weightPerMuscleGroup: [String: Double]
    let weightPerMuscle: [String: Double]
    let repsPerMuscleGroup: [String: Double]
    let repsPerMuscle: [String: Double]
    let setsPerMuscleGroup: [String: Int]
    let setsPerMuscle: [String: Int]
    let intensity: IntensityAnalytics?

    static let empty = WorkoutAnalytics(
        totalSets: 0, totalReps: 0, totalWeight: 0, weightFormat: "kg",
        avgRepsPerSet: 0, avgWeightPerSet: 0, avgWeightPerRep: 0,
        weightPerMuscleGroup: [:], weightPerMuscle: [:],
        repsPerMuscleGroup: [:], repsPerMuscle: [:],
        setsPerMuscleGroup: [:], setsPerMuscle: [:],
        intensity: nil
    )

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
        case intensity
    }

    init(totalSets: Int, totalReps: Int, totalWeight: Double, weightFormat: String,
         avgRepsPerSet: Double, avgWeightPerSet: Double, avgWeightPerRep: Double,
         weightPerMuscleGroup: [String: Double], weightPerMuscle: [String: Double],
         repsPerMuscleGroup: [String: Double], repsPerMuscle: [String: Double],
         setsPerMuscleGroup: [String: Int], setsPerMuscle: [String: Int],
         intensity: IntensityAnalytics? = nil) {
        self.totalSets = totalSets
        self.totalReps = totalReps
        self.totalWeight = totalWeight
        self.weightFormat = weightFormat
        self.avgRepsPerSet = avgRepsPerSet
        self.avgWeightPerSet = avgWeightPerSet
        self.avgWeightPerRep = avgWeightPerRep
        self.weightPerMuscleGroup = weightPerMuscleGroup
        self.weightPerMuscle = weightPerMuscle
        self.repsPerMuscleGroup = repsPerMuscleGroup
        self.repsPerMuscle = repsPerMuscle
        self.setsPerMuscleGroup = setsPerMuscleGroup
        self.setsPerMuscle = setsPerMuscle
        self.intensity = intensity
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.totalSets = try container.decodeIfPresent(Int.self, forKey: .totalSets) ?? 0
        self.totalReps = try container.decodeIfPresent(Int.self, forKey: .totalReps) ?? 0
        self.totalWeight = try container.decodeIfPresent(Double.self, forKey: .totalWeight) ?? 0
        self.weightFormat = try container.decodeIfPresent(String.self, forKey: .weightFormat) ?? "kg"
        self.avgRepsPerSet = try container.decodeIfPresent(Double.self, forKey: .avgRepsPerSet) ?? 0
        self.avgWeightPerSet = try container.decodeIfPresent(Double.self, forKey: .avgWeightPerSet) ?? 0
        self.avgWeightPerRep = try container.decodeIfPresent(Double.self, forKey: .avgWeightPerRep) ?? 0
        self.weightPerMuscleGroup = try container.decodeIfPresent([String: Double].self, forKey: .weightPerMuscleGroup) ?? [:]
        self.weightPerMuscle = try container.decodeIfPresent([String: Double].self, forKey: .weightPerMuscle) ?? [:]
        self.repsPerMuscleGroup = try container.decodeIfPresent([String: Double].self, forKey: .repsPerMuscleGroup) ?? [:]
        self.repsPerMuscle = try container.decodeIfPresent([String: Double].self, forKey: .repsPerMuscle) ?? [:]
        self.setsPerMuscleGroup = try container.decodeIfPresent([String: Int].self, forKey: .setsPerMuscleGroup) ?? [:]
        self.setsPerMuscle = try container.decodeIfPresent([String: Int].self, forKey: .setsPerMuscle) ?? [:]
        self.intensity = try container.decodeIfPresent(IntensityAnalytics.self, forKey: .intensity)
    }
}
