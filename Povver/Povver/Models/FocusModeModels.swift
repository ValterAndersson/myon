/**
 * FocusModeModels.swift
 * 
 * ═══════════════════════════════════════════════════════════════════════════════
 * FOCUS MODE DOMAIN MODELS - Core Data Structures for Workout Execution
 * ═══════════════════════════════════════════════════════════════════════════════
 *
 * PURPOSE:
 * These models represent the domain entities for Focus Mode workout execution.
 * They align with the Firestore schema for proper sync between iOS and backend.
 *
 * ENTITY HIERARCHY:
 * ┌─────────────────────────────────────────────────────────────────────────────┐
 * │  FocusModeWorkout                                                           │
 * │  ├── id: String                 - Document ID                               │
 * │  ├── userId: String             - Owner                                     │
 * │  ├── status: WorkoutStatus      - in_progress / completed / cancelled       │
 * │  ├── exercises: [FocusModeExercise]                                         │
 * │  │   ├── instanceId: String     - Unique per-workout (stable ID)            │
 * │  │   ├── exerciseId: String     - Catalog reference                         │
 * │  │   ├── name: String           - Denormalized display name                 │
 * │  │   ├── position: Int          - Order (0, 1, 2...)                        │
 * │  │   └── sets: [FocusModeSet]                                               │
 * │  │       ├── id: String         - Unique per-workout (stable ID)            │
 * │  │       ├── setType: warmup/working/dropset                                │
 * │  │       ├── status: planned/done/skipped                                   │
 * │  │       ├── target*: Double?/Int?  - Prescription values                   │
 * │  │       └── weight/reps/rir: Actuals (filled when done)                    │
 * │  └── totals: WorkoutTotals      - Computed: sets, reps, volume              │
 * └─────────────────────────────────────────────────────────────────────────────┘
 *
 * KEY DESIGN DECISIONS:
 *
 * 1. SINGLE-VALUE MODEL (Not Target/Actual Split)
 *    - When user edits a value on a planned set, we update target*
 *    - When set is marked done, actuals are filled, targets preserved
 *    - Display logic: show actual if done, target if planned
 *
 * 2. STABLE IDs
 *    - instanceId: Identifies exercise within this workout (UUID)
 *    - exerciseId: Points to catalog (for metadata lookup)
 *    - set.id: Stable set identity (UUID, never changes)
 *    - Why: Enables dependency tracking in MutationCoordinator
 *
 * 3. SYNC STATE (Local Only)
 *    - syncState field tracks sync status for UI indicators
 *    - Not persisted to server (excluded from CodingKeys)
 *    - Used to show spinners/error badges on entities
 *
 * 4. TOTALS COMPUTATION
 *    - Warmups excluded from totals
 *    - Skipped sets excluded from totals
 *    - Only done working/dropset sets count
 *    - Recalculated locally and verified by server
 *
 * BACKEND ALIGNMENT:
 * - CodingKeys use snake_case to match Firestore schema
 * - All optional fields are truly optional in Firestore
 * - Timestamps handled via custom parsing (see FocusModeWorkoutService)
 */

import Foundation

// MARK: - Sync State

/// Sync state for entities (not persisted to server)
enum FocusModeSyncState: Equatable {
    case synced
    case pending
    case failed(String)  // Error message
    
    var isPending: Bool {
        if case .pending = self { return true }
        return false
    }
    
    var isFailed: Bool {
        if case .failed = self { return true }
        return false
    }
}

// MARK: - Set Status

enum FocusModeSetStatus: String, Codable, CaseIterable {
    case planned = "planned"
    case done = "done"
    case skipped = "skipped"
    
    var displayName: String {
        switch self {
        case .planned: return "Planned"
        case .done: return "Done"
        case .skipped: return "Skipped"
        }
    }
}

// MARK: - Set Type

enum FocusModeSetType: String, Codable, CaseIterable {
    case warmup = "warmup"
    case working = "working"
    case dropset = "dropset"
    
    var displayName: String {
        switch self {
        case .warmup: return "Warm-up"
        case .working: return "Working"
        case .dropset: return "Drop Set"
        }
    }
    
    var isCountedInTotals: Bool {
        self == .working || self == .dropset
    }
}

// MARK: - Set Tags

struct FocusModeSetTags: Codable, Equatable {
    var isFailure: Bool?
    
    enum CodingKeys: String, CodingKey {
        case isFailure = "is_failure"
    }
}

// MARK: - Focus Mode Set

struct FocusModeSet: Codable, Identifiable, Equatable {
    let id: String
    var setType: FocusModeSetType
    var status: FocusModeSetStatus
    
    // Target values (from prescription or user edit before done)
    var targetWeight: Double?
    var targetReps: Int?
    var targetRir: Int?
    
    // Actual values (filled when marked done)
    var weight: Double?
    var reps: Int?
    var rir: Int?
    
    var tags: FocusModeSetTags?
    
    /// Sync state (not persisted to server)
    var syncState: FocusModeSyncState = .synced
    
    enum CodingKeys: String, CodingKey {
        case id
        case setType = "set_type"
        case status
        case targetWeight = "target_weight"
        case targetReps = "target_reps"
        case targetRir = "target_rir"
        case weight
        case reps
        case rir
        case tags
    }
    
    // MARK: - Computed Properties
    
    var isWarmup: Bool { setType == .warmup }
    var isDone: Bool { status == .done }
    var isSkipped: Bool { status == .skipped }
    var isPlanned: Bool { status == .planned }
    
    /// Display weight - shows actual if done, target if planned
    var displayWeight: Double? {
        isDone ? weight : targetWeight
    }
    
    /// Display reps - shows actual if done, target if planned
    var displayReps: Int? {
        isDone ? reps : targetReps
    }
    
    /// Display RIR - shows actual if done, target if planned
    var displayRir: Int? {
        isDone ? rir : targetRir
    }
    
    // MARK: - Initializers
    
    init(
        id: String = UUID().uuidString,
        setType: FocusModeSetType = .working,
        status: FocusModeSetStatus = .planned,
        targetWeight: Double? = nil,
        targetReps: Int? = nil,
        targetRir: Int? = nil,
        weight: Double? = nil,
        reps: Int? = nil,
        rir: Int? = nil,
        tags: FocusModeSetTags? = nil
    ) {
        self.id = id
        self.setType = setType
        self.status = status
        self.targetWeight = targetWeight
        self.targetReps = targetReps
        self.targetRir = targetRir
        self.weight = weight
        self.reps = reps
        self.rir = rir
        self.tags = tags
    }
}

// MARK: - Focus Mode Exercise

struct FocusModeExercise: Codable, Identifiable, Equatable {
    let instanceId: String
    var exerciseId: String
    var name: String
    var position: Int
    var sets: [FocusModeSet]
    
    /// Sync state (not persisted to server)
    var syncState: FocusModeSyncState = .synced
    
    var id: String { instanceId }
    
    enum CodingKeys: String, CodingKey {
        case instanceId = "instance_id"
        case exerciseId = "exercise_id"
        case name
        case position
        case sets
        // syncState is not in CodingKeys - not persisted
    }
    
    // MARK: - Computed Properties
    
    var completedSetsCount: Int {
        sets.filter { $0.isDone && $0.setType.isCountedInTotals }.count
    }
    
    var totalWorkingSetsCount: Int {
        sets.filter { $0.setType.isCountedInTotals }.count
    }
    
    var isComplete: Bool {
        sets.allSatisfy { $0.isDone || $0.isSkipped }
    }
    
    // MARK: - Initializers
    
    init(
        instanceId: String = UUID().uuidString,
        exerciseId: String,
        name: String,
        position: Int,
        sets: [FocusModeSet] = []
    ) {
        self.instanceId = instanceId
        self.exerciseId = exerciseId
        self.name = name
        self.position = position
        self.sets = sets
    }
}

// MARK: - Focus Mode Workout

struct FocusModeWorkout: Codable, Identifiable {
    let id: String
    var userId: String
    var status: WorkoutStatus
    var sourceTemplateId: String?
    var sourceRoutineId: String?
    var name: String?
    var exercises: [FocusModeExercise]
    var totals: WorkoutTotals
    var version: Int
    var startTime: Date
    var endTime: Date?
    var createdAt: Date
    var updatedAt: Date?

    enum CodingKeys: String, CodingKey {
        case id
        case userId = "user_id"
        case status
        case sourceTemplateId = "source_template_id"
        case sourceRoutineId = "source_routine_id"
        case name
        case exercises
        case totals
        case version
        case startTime = "start_time"
        case endTime = "end_time"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.id = try container.decode(String.self, forKey: .id)
        self.userId = try container.decode(String.self, forKey: .userId)
        self.status = try container.decode(WorkoutStatus.self, forKey: .status)
        self.sourceTemplateId = try container.decodeIfPresent(String.self, forKey: .sourceTemplateId)
        self.sourceRoutineId = try container.decodeIfPresent(String.self, forKey: .sourceRoutineId)
        self.name = try container.decodeIfPresent(String.self, forKey: .name)
        self.exercises = try container.decode([FocusModeExercise].self, forKey: .exercises)
        self.totals = try container.decode(WorkoutTotals.self, forKey: .totals)
        self.version = try container.decodeIfPresent(Int.self, forKey: .version) ?? 0
        self.startTime = try container.decode(Date.self, forKey: .startTime)
        self.endTime = try container.decodeIfPresent(Date.self, forKey: .endTime)
        self.createdAt = try container.decode(Date.self, forKey: .createdAt)
        self.updatedAt = try container.decodeIfPresent(Date.self, forKey: .updatedAt)
    }

    init(
        id: String,
        userId: String,
        status: WorkoutStatus,
        sourceTemplateId: String? = nil,
        sourceRoutineId: String? = nil,
        name: String? = nil,
        exercises: [FocusModeExercise],
        totals: WorkoutTotals,
        version: Int = 0,
        startTime: Date,
        endTime: Date? = nil,
        createdAt: Date,
        updatedAt: Date? = nil
    ) {
        self.id = id
        self.userId = userId
        self.status = status
        self.sourceTemplateId = sourceTemplateId
        self.sourceRoutineId = sourceRoutineId
        self.name = name
        self.exercises = exercises
        self.totals = totals
        self.version = version
        self.startTime = startTime
        self.endTime = endTime
        self.createdAt = createdAt
        self.updatedAt = updatedAt
    }

    enum WorkoutStatus: String, Codable {
        case inProgress = "in_progress"
        case completed = "completed"
        case cancelled = "cancelled"
    }
}

// MARK: - Workout Totals

struct WorkoutTotals: Codable, Equatable {
    var sets: Int
    var reps: Int
    var volume: Double
    var stimulusScore: Double?
    
    enum CodingKeys: String, CodingKey {
        case sets
        case reps
        case volume
        case stimulusScore = "stimulus_score"
    }
    
    init(sets: Int = 0, reps: Int = 0, volume: Double = 0, stimulusScore: Double? = nil) {
        self.sets = sets
        self.reps = reps
        self.volume = volume
        self.stimulusScore = stimulusScore
    }
}

// MARK: - LogSet DTOs (needed by service)

struct LogSetRequest: Encodable {
    let workoutId: String
    let exerciseInstanceId: String
    let setId: String
    let values: SetValues
    let isFailure: Bool?
    let idempotencyKey: String
    let clientTimestamp: String
    
    enum CodingKeys: String, CodingKey {
        case workoutId = "workout_id"
        case exerciseInstanceId = "exercise_instance_id"
        case setId = "set_id"
        case values
        case isFailure = "is_failure"
        case idempotencyKey = "idempotency_key"
        case clientTimestamp = "client_timestamp"
    }
    
    struct SetValues: Encodable {
        let weight: Double?
        let reps: Int
        let rir: Int?
    }
}

struct LogSetResponse: Decodable {
    let success: Bool
    let eventId: String?
    let totals: WorkoutTotals?
    let version: Int?
    let error: String?

    enum CodingKeys: String, CodingKey {
        case success
        case data
        case error
    }

    private struct DataWrapper: Decodable {
        let eventId: String?
        let totals: WorkoutTotals?
        let version: Int?
        let success: Bool?

        enum CodingKeys: String, CodingKey {
            case eventId = "event_id"
            case totals
            case version
            case success
        }
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.success = try container.decodeIfPresent(Bool.self, forKey: .success) ?? true
        self.error = try container.decodeIfPresent(String.self, forKey: .error)

        // API returns { data: { event_id, totals, version, success }, success: true }
        if let dataWrapper = try container.decodeIfPresent(DataWrapper.self, forKey: .data) {
            self.eventId = dataWrapper.eventId
            self.totals = dataWrapper.totals
            self.version = dataWrapper.version
        } else {
            self.eventId = nil
            self.totals = nil
            self.version = nil
        }
    }
}

// MARK: - Autofill DTOs (needed by service)

struct AutofillSetUpdate: Encodable {
    let setId: String
    let weight: Double?
    let reps: Int?
    let rir: Int?
    
    enum CodingKeys: String, CodingKey {
        case setId = "set_id"
        case weight
        case reps
        case rir
    }
}

struct AutofillSetAddition: Encodable {
    let id: String
    let setType: String
    let weight: Double?
    let reps: Int
    let rir: Int?
    
    enum CodingKeys: String, CodingKey {
        case id
        case setType = "set_type"
        case weight
        case reps
        case rir
    }
}

struct AutofillExerciseRequest: Encodable {
    let workoutId: String
    let exerciseInstanceId: String
    let updates: [AutofillSetUpdate]
    let additions: [AutofillSetAddition]
    let idempotencyKey: String
    let clientTimestamp: String
    
    enum CodingKeys: String, CodingKey {
        case workoutId = "workout_id"
        case exerciseInstanceId = "exercise_instance_id"
        case updates
        case additions
        case idempotencyKey = "idempotency_key"
        case clientTimestamp = "client_timestamp"
    }
}

struct AutofillExerciseResponse: Decodable {
    let success: Bool
    let eventId: String?
    let totals: WorkoutTotals?
    let version: Int?
    let error: String?

    enum CodingKeys: String, CodingKey {
        case success
        case data
        case error
    }

    private struct DataWrapper: Decodable {
        let eventId: String?
        let totals: WorkoutTotals?
        let version: Int?
        let success: Bool?

        enum CodingKeys: String, CodingKey {
            case eventId = "event_id"
            case totals
            case version
            case success
        }
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.success = try container.decodeIfPresent(Bool.self, forKey: .success) ?? true
        self.error = try container.decodeIfPresent(String.self, forKey: .error)

        // API returns { data: { event_id, totals, version, success }, success: true }
        if let dataWrapper = try container.decodeIfPresent(DataWrapper.self, forKey: .data) {
            self.eventId = dataWrapper.eventId
            self.totals = dataWrapper.totals
            self.version = dataWrapper.version
        } else {
            self.eventId = nil
            self.totals = nil
            self.version = nil
        }
    }
}
