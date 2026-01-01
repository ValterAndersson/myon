/**
 * FocusModeModels.swift
 * 
 * Core domain models for Focus Mode Workout Execution.
 * These align with the backend schema for proper sync.
 * 
 * Note: Request/Response DTOs are private to FocusModeWorkoutService.
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
        case startTime = "start_time"
        case endTime = "end_time"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
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
    let error: String?
    
    enum CodingKeys: String, CodingKey {
        case success
        case eventId = "event_id"
        case totals
        case error
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
    let error: String?
    
    enum CodingKeys: String, CodingKey {
        case success
        case eventId = "event_id"
        case totals
        case error
    }
}
