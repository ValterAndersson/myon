/**
 * FocusModeWorkoutService.swift
 * 
 * Service layer for Focus Mode workout execution.
 * Handles all backend API calls for active workout operations.
 * 
 * Per FOCUS_MODE_WORKOUT_EXECUTION.md spec:
 * - Cell edits: local UI update immediately; backend sync async
 * - Set done: must feel instant; backend sync async; any AI follow-up async
 * - AI inline action: target < 1.0–1.5s perceived
 */

import Foundation
import Combine
import UIKit

@MainActor
class FocusModeWorkoutService: ObservableObject {
    
    // MARK: - Published State
    
    @Published private(set) var workout: FocusModeWorkout?
    @Published private(set) var isLoading: Bool = false
    @Published private(set) var error: String?
    @Published private(set) var isSyncing: Bool = false
    
    /// Track exercises that are currently being synced to the server
    /// Patches to sets in these exercises should wait for sync to complete
    @Published private(set) var pendingSyncExercises: Set<String> = []
    
    /// Track sets that are currently being synced
    @Published private(set) var pendingSyncSets: Set<String> = []
    
    /// Continuations waiting for exercise sync to complete
    private var syncContinuations: [String: [CheckedContinuation<Void, Never>]] = [:]
    
    // MARK: - Dependencies
    
    private let apiClient = ApiClient.shared
    private let idempotencyHelper = IdempotencyKeyHelper.shared
    
    // MARK: - Singleton (optional - can also inject)
    
    static let shared = FocusModeWorkoutService()
    
    private init() {}
    
    // MARK: - Workout Lifecycle
    
    /// Start a new active workout
    func startWorkout(
        name: String? = nil,
        sourceTemplateId: String? = nil,
        sourceRoutineId: String? = nil,
        exercises: [FocusModeExercise] = []
    ) async throws -> FocusModeWorkout {
        isLoading = true
        defer { isLoading = false }
        
        let request = StartActiveWorkoutRequest(
            name: name,
            sourceTemplateId: sourceTemplateId,
            sourceRoutineId: sourceRoutineId,
            exercises: exercises.isEmpty ? nil : exercises.map { ExerciseDTO(from: $0) }
        )
        
        let response: StartActiveWorkoutResponse = try await apiClient.postJSON("startActiveWorkout", body: request)
        
        guard response.success else {
            throw FocusModeError.startFailed(response.error ?? "Unknown error")
        }
        
        // Parse all fields from server (fall back to sensible defaults only if missing)
        let serverStartTime = parseISO8601Date(response.startTime) ?? Date()
        let serverEndTime = parseISO8601Date(response.endTime)
        let serverCreatedAt = parseISO8601Date(response.createdAt) ?? Date()
        let serverUpdatedAt = parseISO8601Date(response.updatedAt)
        
        // Parse status from server (default to inProgress for new workouts)
        let serverStatus: FocusModeWorkout.WorkoutStatus
        if let statusString = response.status {
            serverStatus = FocusModeWorkout.WorkoutStatus(rawValue: statusString) ?? .inProgress
        } else {
            serverStatus = .inProgress
        }
        
        // Parse the workout using all server-provided data
        let parsedWorkout = FocusModeWorkout(
            id: response.workoutId ?? UUID().uuidString,
            userId: response.userId ?? "",
            status: serverStatus,
            sourceTemplateId: response.sourceTemplateId ?? sourceTemplateId,
            sourceRoutineId: response.sourceRoutineId ?? sourceRoutineId,
            name: response.name ?? name,
            exercises: response.exercises?.map { FocusModeExercise(from: $0) } ?? [],
            totals: response.totals ?? WorkoutTotals(),
            startTime: serverStartTime,
            endTime: serverEndTime,
            createdAt: serverCreatedAt,
            updatedAt: serverUpdatedAt
        )
        
        self.workout = parsedWorkout
        return parsedWorkout
    }
    
    /// Load existing active workout (for resume)
    func loadWorkout(workoutId: String) async throws {
        isLoading = true
        defer { isLoading = false }
        
        // TODO: Call getActiveWorkout endpoint
    }
    
    // MARK: - Log Set (Hot Path)
    
    /// Mark a set as done - this is the PRIMARY action in focus mode
    /// Must feel instant - apply locally first, sync async
    func logSet(
        exerciseInstanceId: String,
        setId: String,
        weight: Double?,
        reps: Int,
        rir: Int?,
        isFailure: Bool? = nil
    ) async throws -> WorkoutTotals {
        guard let workout = workout else {
            throw FocusModeError.noActiveWorkout
        }
        
        // Wait for exercise to finish syncing before logging
        if pendingSyncExercises.contains(exerciseInstanceId) {
            try await waitForExerciseSync(exerciseInstanceId)
        }
        
        // 1. Apply optimistically to local state
        applyLogSetLocally(exerciseInstanceId: exerciseInstanceId, setId: setId, weight: weight, reps: reps, rir: rir, isFailure: isFailure)
        
        // 2. Generate idempotency key
        let idempotencyKey = idempotencyHelper.generate(
            context: "logSet",
            exerciseId: exerciseInstanceId,
            setId: setId
        )
        
        // 3. Build request
        let request = LogSetRequest(
            workoutId: workout.id,
            exerciseInstanceId: exerciseInstanceId,
            setId: setId,
            values: LogSetRequest.SetValues(weight: weight, reps: reps, rir: rir),
            isFailure: isFailure,
            idempotencyKey: idempotencyKey,
            clientTimestamp: ISO8601DateFormatter().string(from: Date())
        )
        
        // 4. Sync to backend
        isSyncing = true
        defer { isSyncing = false }
        
        do {
            let response: LogSetResponse = try await apiClient.postJSON("logSet", body: request)
            
            if response.success, let totals = response.totals {
                // Update totals from server (source of truth)
                self.workout?.totals = totals
                return totals
            } else {
                throw FocusModeError.syncFailed(response.error ?? "Unknown error")
            }
        } catch {
            // Log sync failure but don't rollback local state
            // User can continue working offline
            print("[FocusModeWorkoutService] logSet sync failed: \(error)")
            self.error = "Sync pending - you can continue"
            throw error
        }
    }
    
    // MARK: - Patch Active Workout
    
    /// Edit a field value (weight, reps, rir, etc.)
    func patchField(
        exerciseInstanceId: String,
        setId: String,
        field: String,
        value: Any
    ) async throws -> WorkoutTotals {
        guard let workout = workout else {
            throw FocusModeError.noActiveWorkout
        }
        
        // Wait for exercise to finish syncing before patching
        if pendingSyncExercises.contains(exerciseInstanceId) {
            try await waitForExerciseSync(exerciseInstanceId)
        }
        
        // 1. Apply optimistically
        applyPatchLocally(exerciseInstanceId: exerciseInstanceId, setId: setId, field: field, value: value)
        
        // 2. Generate idempotency key
        let idempotencyKey = idempotencyHelper.generate(
            context: "patch",
            exerciseId: exerciseInstanceId,
            setId: setId,
            field: field
        )
        
        // 3. Build request
        let op = PatchOperationDTO(
            op: "set_field",
            target: PatchTargetDTO(exerciseInstanceId: exerciseInstanceId, setId: setId),
            field: field,
            value: AnyCodable(value)
        )
        
        let request = PatchActiveWorkoutRequest(
            workoutId: workout.id,
            ops: [op],
            cause: "user_edit",
            uiSource: "cell_edit",
            idempotencyKey: idempotencyKey,
            clientTimestamp: ISO8601DateFormatter().string(from: Date()),
            aiScope: nil
        )
        
        // 4. Sync to backend (debounced in production)
        return try await syncPatch(request)
    }
    
    /// Add a new set to an exercise
    func addSet(
        exerciseInstanceId: String,
        setType: FocusModeSetType = .working,
        weight: Double? = nil,
        reps: Int = 10,
        rir: Int? = 2
    ) async throws -> WorkoutTotals {
        guard let workout = workout else {
            throw FocusModeError.noActiveWorkout
        }
        
        let newSetId = UUID().uuidString
        
        // 1. Apply optimistically
        let newSet = FocusModeSet(
            id: newSetId,
            setType: setType,
            status: .planned,
            targetWeight: weight,
            targetReps: reps,
            targetRir: rir
        )
        addSetLocally(exerciseInstanceId: exerciseInstanceId, set: newSet)
        
        // 2. Build request - use reps/rir/weight (not target_*) per backend schema
        let idempotencyKey = idempotencyHelper.generate(context: "addSet", setId: newSetId)
        
        // Use typed struct to ensure proper JSON encoding
        let addSetValue = AddSetValueDTO(
            id: newSetId,
            setType: setType.rawValue,
            status: "planned",
            reps: reps,
            rir: rir ?? 2,
            weight: weight  // Nullable for bodyweight
        )
        
        let request = AddSetPatchRequest(
            workoutId: workout.id,
            op: AddSetOperationDTO(
                op: "add_set",
                target: PatchTargetDTO(exerciseInstanceId: exerciseInstanceId, setId: nil),
                value: addSetValue
            ),
            cause: "user_edit",
            uiSource: "add_set_button",
            idempotencyKey: idempotencyKey,
            clientTimestamp: ISO8601DateFormatter().string(from: Date())
        )
        
        return try await syncAddSetPatch(request)
    }
    
    /// Add a new exercise to the workout
    /// NOTE: Does NOT use optimistic updates to avoid race conditions.
    /// Exercise only appears after server confirmation.
    func addExercise(
        exercise: Exercise,
        withSets initialSets: [FocusModeSet]? = nil
    ) async throws {
        guard let workout = workout else {
            throw FocusModeError.noActiveWorkout
        }
        
        let newInstanceId = UUID().uuidString
        let defaultSets = initialSets ?? [
            FocusModeSet(
                id: UUID().uuidString,
                setType: .working,
                status: .planned,
                targetReps: 10,
                targetRir: 2
            )
        ]
        
        let newExercise = FocusModeExercise(
            instanceId: newInstanceId,
            exerciseId: exercise.id,
            name: exercise.name,
            position: workout.exercises.count,
            sets: defaultSets
        )
        
        // Use dedicated addExercise endpoint
        let request = AddExerciseRequest(
            workoutId: workout.id,
            instanceId: newInstanceId,
            exerciseId: exercise.id,
            name: exercise.name,
            position: newExercise.position,
            sets: defaultSets.map { AddExerciseSetDTO(from: $0) }
        )
        
        isSyncing = true
        defer { isSyncing = false }
        
        print("[addExercise] Sending exercise with sets: \(defaultSets.map { $0.id })")
        
        let response: AddExerciseResponse = try await apiClient.postJSON("addExercise", body: request)
        
        if !response.success {
            throw FocusModeError.syncFailed(response.error ?? "Failed to add exercise")
        }
        
        // Only add to local state AFTER server confirmation
        var updatedWorkout = self.workout!
        updatedWorkout.exercises.append(newExercise)
        self.workout = updatedWorkout
        
        print("[addExercise] Added exercise to local state with sets: \(newExercise.sets.map { $0.id })")
        
        UIImpactFeedbackGenerator(style: .medium).impactOccurred()
    }
    
    /// Remove a set from an exercise
    func removeSet(
        exerciseInstanceId: String,
        setId: String
    ) async throws -> WorkoutTotals {
        guard let workout = workout else {
            throw FocusModeError.noActiveWorkout
        }
        
        // 1. Apply optimistically
        removeSetLocally(exerciseInstanceId: exerciseInstanceId, setId: setId)
        
        // 2. Build request
        let idempotencyKey = idempotencyHelper.generate(context: "removeSet", setId: setId)
        
        let op = PatchOperationDTO(
            op: "remove_set",
            target: PatchTargetDTO(exerciseInstanceId: exerciseInstanceId, setId: setId),
            field: nil,
            value: nil
        )
        
        let request = PatchActiveWorkoutRequest(
            workoutId: workout.id,
            ops: [op],
            cause: "user_edit",
            uiSource: "swipe_delete",
            idempotencyKey: idempotencyKey,
            clientTimestamp: ISO8601DateFormatter().string(from: Date()),
            aiScope: nil
        )
        
        return try await syncPatch(request)
    }
    
    // MARK: - Workout Lifecycle Actions
    
    /// Cancel (discard) the active workout
    func cancelWorkout() async throws {
        guard let workout = workout else {
            throw FocusModeError.noActiveWorkout
        }
        
        let request = CancelWorkoutRequest(workoutId: workout.id)
        
        isLoading = true
        defer { isLoading = false }
        
        let response: CancelWorkoutResponse = try await apiClient.postJSON("cancelActiveWorkout", body: request)
        
        if response.success {
            self.workout = nil  // Clear local state
        } else {
            throw FocusModeError.syncFailed(response.error ?? "Failed to cancel workout")
        }
    }
    
    /// Complete (finish) the active workout
    func completeWorkout() async throws -> String {
        guard let workout = workout else {
            throw FocusModeError.noActiveWorkout
        }
        
        let request = CompleteWorkoutRequest(workoutId: workout.id)
        
        isLoading = true
        defer { isLoading = false }
        
        let response: CompleteWorkoutResponse = try await apiClient.postJSON("completeActiveWorkout", body: request)
        
        if response.success {
            let archivedId = response.workoutId ?? workout.id
            self.workout = nil  // Clear local state
            return archivedId
        } else {
            throw FocusModeError.syncFailed(response.error ?? "Failed to complete workout")
        }
    }
    
    /// Update the workout name
    func updateWorkoutName(_ name: String) async throws {
        guard let workout = workout else {
            throw FocusModeError.noActiveWorkout
        }
        
        // For now, use patchActiveWorkout with a special op
        // TODO: Add proper name update op to backend
        // Optimistically update local state
        self.workout?.name = name
    }
    
    /// Reorder exercises locally
    /// NOTE: Currently local-only, backend sync not implemented yet
    func reorderExercises(from source: IndexSet, to destination: Int) {
        guard var workout = workout else { return }
        
        workout.exercises.move(fromOffsets: source, toOffset: destination)
        
        // Update positions to match new order
        for (index, _) in workout.exercises.enumerated() {
            workout.exercises[index].position = index
        }
        
        self.workout = workout
        
        // TODO: Sync to backend when reorder endpoint is available
        print("[FocusModeWorkoutService] Reordered exercises locally")
    }
    
    // MARK: - AI Actions
    
    /// Autofill exercise with AI prescription
    func autofillExercise(
        exerciseInstanceId: String,
        updates: [AutofillSetUpdate],
        additions: [AutofillSetAddition]
    ) async throws -> WorkoutTotals {
        guard let workout = workout else {
            throw FocusModeError.noActiveWorkout
        }
        
        let idempotencyKey = idempotencyHelper.generate(context: "autofill", exerciseId: exerciseInstanceId)
        
        let request = AutofillExerciseRequest(
            workoutId: workout.id,
            exerciseInstanceId: exerciseInstanceId,
            updates: updates,
            additions: additions,
            idempotencyKey: idempotencyKey,
            clientTimestamp: ISO8601DateFormatter().string(from: Date())
        )
        
        isSyncing = true
        defer { isSyncing = false }
        
        let response: AutofillExerciseResponse = try await apiClient.postJSON("autofillExercise", body: request)
        
        if response.success, let totals = response.totals {
            // Apply updates locally
            applyAutofillLocally(exerciseInstanceId: exerciseInstanceId, updates: updates, additions: additions)
            self.workout?.totals = totals
            return totals
        } else {
            throw FocusModeError.autofillFailed(response.error ?? "Unknown error")
        }
    }
    
    // MARK: - Private Helpers
    
    /// Wait for an exercise to finish syncing (max 3 seconds)
    private func waitForExerciseSync(_ exerciseInstanceId: String) async throws {
        let maxWaitTime: TimeInterval = 3.0
        let pollInterval: TimeInterval = 0.1
        let startTime = Date()
        
        while pendingSyncExercises.contains(exerciseInstanceId) {
            if Date().timeIntervalSince(startTime) > maxWaitTime {
                // Timeout - proceed anyway, server will return 404 and user can retry
                print("[FocusModeWorkoutService] Timeout waiting for exercise sync: \(exerciseInstanceId)")
                break
            }
            try await Task.sleep(nanoseconds: UInt64(pollInterval * 1_000_000_000))
        }
    }
    
    private func syncPatch(_ request: PatchActiveWorkoutRequest) async throws -> WorkoutTotals {
        isSyncing = true
        defer { isSyncing = false }
        
        let response: PatchActiveWorkoutResponse = try await apiClient.postJSON("patchActiveWorkout", body: request)
        
        if response.success, let totals = response.totals {
            self.workout?.totals = totals
            return totals
        } else {
            throw FocusModeError.syncFailed(response.error ?? "Unknown error")
        }
    }
    
    private func syncAddSetPatch(_ request: AddSetPatchRequest) async throws -> WorkoutTotals {
        isSyncing = true
        defer { isSyncing = false }
        
        let response: PatchActiveWorkoutResponse = try await apiClient.postJSON("patchActiveWorkout", body: request)
        
        if response.success, let totals = response.totals {
            self.workout?.totals = totals
            return totals
        } else {
            throw FocusModeError.syncFailed(response.error ?? "Unknown error")
        }
    }
    
    // MARK: - Optimistic Updates
    
    private func applyLogSetLocally(
        exerciseInstanceId: String,
        setId: String,
        weight: Double?,
        reps: Int,
        rir: Int?,
        isFailure: Bool?
    ) {
        guard var workout = workout else { return }
        
        if let exIdx = workout.exercises.firstIndex(where: { $0.instanceId == exerciseInstanceId }),
           let setIdx = workout.exercises[exIdx].sets.firstIndex(where: { $0.id == setId }) {
            
            // Track if this is a new completion (for incrementing totals)
            let wasPlanned = workout.exercises[exIdx].sets[setIdx].status == .planned
            
            workout.exercises[exIdx].sets[setIdx].status = .done
            workout.exercises[exIdx].sets[setIdx].weight = weight
            workout.exercises[exIdx].sets[setIdx].reps = reps
            workout.exercises[exIdx].sets[setIdx].rir = rir
            if let isFailure = isFailure {
                workout.exercises[exIdx].sets[setIdx].tags = FocusModeSetTags(isFailure: isFailure)
            }
            
            // Recalculate totals locally for immediate UI feedback
            if wasPlanned {
                workout.totals = recalculateTotals(for: workout)
            }
            
            self.workout = workout
        }
    }
    
    /// Recalculate workout totals from current state
    private func recalculateTotals(for workout: FocusModeWorkout) -> WorkoutTotals {
        var totalSets = 0
        var totalReps = 0
        var totalVolume: Double = 0
        
        for exercise in workout.exercises {
            for set in exercise.sets where set.status == .done {
                totalSets += 1
                let setReps = set.reps ?? 0
                totalReps += setReps
                totalVolume += (set.weight ?? 0) * Double(setReps)
            }
        }
        
        return WorkoutTotals(sets: totalSets, reps: totalReps, volume: totalVolume)
    }
    
    private func applyPatchLocally(
        exerciseInstanceId: String,
        setId: String,
        field: String,
        value: Any
    ) {
        guard var workout = workout else { return }
        
        if let exIdx = workout.exercises.firstIndex(where: { $0.instanceId == exerciseInstanceId }),
           let setIdx = workout.exercises[exIdx].sets.firstIndex(where: { $0.id == setId }) {
            
            switch field {
            case "weight":
                if let doubleValue = value as? Double {
                    if workout.exercises[exIdx].sets[setIdx].isPlanned {
                        workout.exercises[exIdx].sets[setIdx].targetWeight = doubleValue
                    } else {
                        workout.exercises[exIdx].sets[setIdx].weight = doubleValue
                    }
                }
            case "reps":
                if let intValue = value as? Int {
                    if workout.exercises[exIdx].sets[setIdx].isPlanned {
                        workout.exercises[exIdx].sets[setIdx].targetReps = intValue
                    } else {
                        workout.exercises[exIdx].sets[setIdx].reps = intValue
                    }
                }
            case "rir":
                if let intValue = value as? Int {
                    if workout.exercises[exIdx].sets[setIdx].isPlanned {
                        workout.exercises[exIdx].sets[setIdx].targetRir = intValue
                    } else {
                        workout.exercises[exIdx].sets[setIdx].rir = intValue
                    }
                }
            case "status":
                if let stringValue = value as? String,
                   let status = FocusModeSetStatus(rawValue: stringValue) {
                    workout.exercises[exIdx].sets[setIdx].status = status
                }
            case "set_type":
                if let stringValue = value as? String,
                   let setType = FocusModeSetType(rawValue: stringValue) {
                    workout.exercises[exIdx].sets[setIdx].setType = setType
                }
            case "tags.is_failure":
                if let boolValue = value as? Bool {
                    if workout.exercises[exIdx].sets[setIdx].tags == nil {
                        workout.exercises[exIdx].sets[setIdx].tags = FocusModeSetTags(isFailure: boolValue)
                    } else {
                        workout.exercises[exIdx].sets[setIdx].tags?.isFailure = boolValue
                    }
                }
            default:
                break
            }
            
            self.workout = workout
        }
    }
    
    private func addSetLocally(exerciseInstanceId: String, set: FocusModeSet) {
        guard var workout = workout else { return }
        
        if let exIdx = workout.exercises.firstIndex(where: { $0.instanceId == exerciseInstanceId }) {
            workout.exercises[exIdx].sets.append(set)
            self.workout = workout
        }
    }
    
    private func removeSetLocally(exerciseInstanceId: String, setId: String) {
        guard var workout = workout else { return }
        
        if let exIdx = workout.exercises.firstIndex(where: { $0.instanceId == exerciseInstanceId }) {
            // Check if the removed set was completed (affects totals)
            let wasCompleted = workout.exercises[exIdx].sets.first(where: { $0.id == setId })?.status == .done
            
            workout.exercises[exIdx].sets.removeAll { $0.id == setId }
            
            // Recalculate totals if a completed set was removed
            if wasCompleted {
                workout.totals = recalculateTotals(for: workout)
            }
            
            self.workout = workout
        }
    }
    
    private func applyAutofillLocally(
        exerciseInstanceId: String,
        updates: [AutofillSetUpdate],
        additions: [AutofillSetAddition]
    ) {
        guard var workout = workout else { return }
        
        if let exIdx = workout.exercises.firstIndex(where: { $0.instanceId == exerciseInstanceId }) {
            for update in updates {
                if let setIdx = workout.exercises[exIdx].sets.firstIndex(where: { $0.id == update.setId }) {
                    if let weight = update.weight { workout.exercises[exIdx].sets[setIdx].targetWeight = weight }
                    if let reps = update.reps { workout.exercises[exIdx].sets[setIdx].targetReps = reps }
                    if let rir = update.rir { workout.exercises[exIdx].sets[setIdx].targetRir = rir }
                }
            }
            
            for addition in additions {
                let newSet = FocusModeSet(
                    id: addition.id,
                    setType: FocusModeSetType(rawValue: addition.setType) ?? .working,
                    status: .planned,
                    targetWeight: addition.weight,
                    targetReps: addition.reps,
                    targetRir: addition.rir
                )
                workout.exercises[exIdx].sets.append(newSet)
            }
            
            self.workout = workout
        }
    }
}

// MARK: - Request/Response DTOs

private struct StartActiveWorkoutRequest: Encodable {
    let name: String?
    let sourceTemplateId: String?
    let sourceRoutineId: String?
    let exercises: [ExerciseDTO]?
    
    enum CodingKeys: String, CodingKey {
        case name
        case sourceTemplateId = "source_template_id"
        case sourceRoutineId = "source_routine_id"
        case exercises
    }
}

/// The server wraps the workout data in a "data" object
private struct StartActiveWorkoutResponse: Decodable {
    let success: Bool
    let data: StartActiveWorkoutData?
    let error: String?
    
    // Convenience accessors that unwrap from data
    var workoutId: String? { data?.workoutId ?? data?.activeWorkoutDoc?.id }
    var userId: String? { data?.activeWorkoutDoc?.userId }
    var name: String? { data?.activeWorkoutDoc?.name }
    var status: String? { data?.activeWorkoutDoc?.status }
    var exercises: [ExerciseDTO]? { nil } // Parse from activeWorkoutDoc if needed
    var totals: WorkoutTotals? { data?.activeWorkoutDoc?.totals }
    var sourceTemplateId: String? { data?.activeWorkoutDoc?.sourceTemplateId }
    var sourceRoutineId: String? { data?.activeWorkoutDoc?.sourceRoutineId }
    var startTime: String? { nil } // Firebase timestamps don't serialize as strings
    var endTime: String? { nil }
    var createdAt: String? { nil }
    var updatedAt: String? { nil }
}

private struct StartActiveWorkoutData: Decodable {
    let workoutId: String?
    let activeWorkoutDoc: StartActiveWorkoutDocDTO?
    
    enum CodingKeys: String, CodingKey {
        case workoutId = "workout_id"
        case activeWorkoutDoc = "active_workout_doc"
    }
}

private struct StartActiveWorkoutDocDTO: Decodable {
    let id: String?
    let userId: String?
    let name: String?
    let status: String?
    let totals: WorkoutTotals?
    let sourceTemplateId: String?
    let sourceRoutineId: String?
    
    enum CodingKeys: String, CodingKey {
        case id
        case userId = "user_id"
        case name
        case status
        case totals
        case sourceTemplateId = "source_template_id"
        case sourceRoutineId = "source_routine_id"
    }
}

private struct ExerciseDTO: Codable {
    let instanceId: String
    let exerciseId: String
    let name: String
    let position: Int
    let sets: [SetDTO]
    
    enum CodingKeys: String, CodingKey {
        case instanceId = "instance_id"
        case exerciseId = "exercise_id"
        case name
        case position
        case sets
    }
    
    init(from exercise: FocusModeExercise) {
        self.instanceId = exercise.instanceId
        self.exerciseId = exercise.exerciseId
        self.name = exercise.name
        self.position = exercise.position
        self.sets = exercise.sets.map { SetDTO(from: $0) }
    }
}

private struct SetDTO: Codable {
    let id: String
    let setType: String
    let status: String
    let weight: Double?
    let reps: Int?
    let rir: Int?
    
    enum CodingKeys: String, CodingKey {
        case id
        case setType = "set_type"
        case status
        case weight
        case reps
        case rir
    }
    
    init(from set: FocusModeSet) {
        self.id = set.id
        self.setType = set.setType.rawValue
        self.status = set.status.rawValue
        self.weight = set.targetWeight ?? set.weight
        self.reps = set.targetReps ?? set.reps
        self.rir = set.targetRir ?? set.rir
    }
}

private struct PatchOperationDTO: Encodable {
    let op: String
    let target: PatchTargetDTO
    let field: String?
    let value: AnyCodable?
}

// MARK: - Add Set Operation DTOs

/// Typed DTO for add_set operation to ensure proper JSON encoding
private struct AddSetOperationDTO: Encodable {
    let op: String
    let target: PatchTargetDTO
    let value: AddSetValueDTO
}

/// Typed value for add_set (matches backend Zod schema exactly)
private struct AddSetValueDTO: Encodable {
    let id: String
    let setType: String
    let status: String
    let reps: Int
    let rir: Int
    let weight: Double?  // Nullable for bodyweight
    
    enum CodingKeys: String, CodingKey {
        case id
        case setType = "set_type"
        case status
        case reps
        case rir
        case weight
    }
}

private struct PatchTargetDTO: Encodable {
    let exerciseInstanceId: String
    let setId: String?
    
    enum CodingKeys: String, CodingKey {
        case exerciseInstanceId = "exercise_instance_id"
        case setId = "set_id"
    }
}

private struct PatchActiveWorkoutRequest: Encodable {
    let workoutId: String
    let ops: [PatchOperationDTO]
    let cause: String
    let uiSource: String
    let idempotencyKey: String
    let clientTimestamp: String
    let aiScope: AIScopeDTO?
    
    enum CodingKeys: String, CodingKey {
        case workoutId = "workout_id"
        case ops
        case cause
        case uiSource = "ui_source"
        case idempotencyKey = "idempotency_key"
        case clientTimestamp = "client_timestamp"
        case aiScope = "ai_scope"
    }
}

private struct AIScopeDTO: Encodable {
    let exerciseInstanceId: String
    
    enum CodingKeys: String, CodingKey {
        case exerciseInstanceId = "exercise_instance_id"
    }
}

private struct PatchActiveWorkoutResponse: Decodable {
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

/// Specialized request for add_set to ensure proper encoding (wraps single op in array)
private struct AddSetPatchRequest: Encodable {
    let workoutId: String
    let op: AddSetOperationDTO
    let cause: String
    let uiSource: String
    let idempotencyKey: String
    let clientTimestamp: String
    
    enum CodingKeys: String, CodingKey {
        case workoutId = "workout_id"
        case ops
        case cause
        case uiSource = "ui_source"
        case idempotencyKey = "idempotency_key"
        case clientTimestamp = "client_timestamp"
    }
    
    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(workoutId, forKey: .workoutId)
        try container.encode([op], forKey: .ops)  // Wrap single op in array
        try container.encode(cause, forKey: .cause)
        try container.encode(uiSource, forKey: .uiSource)
        try container.encode(idempotencyKey, forKey: .idempotencyKey)
        try container.encode(clientTimestamp, forKey: .clientTimestamp)
    }
}

// MARK: - Cancel/Complete DTOs

private struct CancelWorkoutRequest: Encodable {
    let workoutId: String
    
    enum CodingKeys: String, CodingKey {
        case workoutId = "workout_id"
    }
}

private struct CancelWorkoutResponse: Decodable {
    let success: Bool
    let error: String?
    
    // Handle nested data structure
    enum CodingKeys: String, CodingKey {
        case success
        case data
        case error
    }
    
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.success = try container.decodeIfPresent(Bool.self, forKey: .success) ?? true
        self.error = try container.decodeIfPresent(String.self, forKey: .error)
    }
}

private struct CompleteWorkoutRequest: Encodable {
    let workoutId: String
    
    enum CodingKeys: String, CodingKey {
        case workoutId = "workout_id"
    }
}

private struct CompleteWorkoutResponse: Decodable {
    let success: Bool
    let workoutId: String?
    let error: String?
    
    enum CodingKeys: String, CodingKey {
        case success
        case data
        case error
    }
    
    private struct DataWrapper: Decodable {
        let workoutId: String?
        
        enum CodingKeys: String, CodingKey {
            case workoutId = "workout_id"
        }
    }
    
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.success = try container.decodeIfPresent(Bool.self, forKey: .success) ?? true
        self.error = try container.decodeIfPresent(String.self, forKey: .error)
        
        if let data = try container.decodeIfPresent(DataWrapper.self, forKey: .data) {
            self.workoutId = data.workoutId
        } else {
            self.workoutId = nil
        }
    }
}

// MARK: - Add Exercise DTOs

private struct AddExerciseRequest: Encodable {
    let workoutId: String
    let instanceId: String
    let exerciseId: String
    let name: String
    let position: Int
    let sets: [AddExerciseSetDTO]
    
    enum CodingKeys: String, CodingKey {
        case workoutId = "workout_id"
        case instanceId = "instance_id"
        case exerciseId = "exercise_id"
        case name
        case position
        case sets
    }
}

private struct AddExerciseSetDTO: Encodable {
    let id: String
    let setType: String
    let status: String
    let targetReps: Int?
    let targetRir: Int?
    let targetWeight: Double?
    
    enum CodingKeys: String, CodingKey {
        case id
        case setType = "set_type"
        case status
        case targetReps = "target_reps"
        case targetRir = "target_rir"
        case targetWeight = "target_weight"
    }
    
    init(from set: FocusModeSet) {
        self.id = set.id
        self.setType = set.setType.rawValue
        self.status = set.status.rawValue
        self.targetReps = set.targetReps
        self.targetRir = set.targetRir
        self.targetWeight = set.targetWeight
    }
}

private struct AddExerciseResponse: Decodable {
    let success: Bool
    let exerciseInstanceId: String?
    let totals: WorkoutTotals?
    let error: String?
    
    enum CodingKeys: String, CodingKey {
        case success
        case exerciseInstanceId = "exercise_instance_id"
        case totals
        case error
    }
}

// MARK: - Extensions for DTO conversion

extension FocusModeExercise {
    fileprivate init(from dto: ExerciseDTO) {
        self.init(
            instanceId: dto.instanceId,
            exerciseId: dto.exerciseId,
            name: dto.name,
            position: dto.position,
            sets: dto.sets.map { FocusModeSet(from: $0) }
        )
    }
}

extension FocusModeSet {
    fileprivate init(from dto: SetDTO) {
        self.init(
            id: dto.id,
            setType: FocusModeSetType(rawValue: dto.setType) ?? .working,
            status: FocusModeSetStatus(rawValue: dto.status) ?? .planned,
            targetWeight: dto.weight,
            targetReps: dto.reps,
            targetRir: dto.rir,
            weight: dto.weight,
            reps: dto.reps,
            rir: dto.rir
        )
    }
}

// MARK: - Errors

enum FocusModeError: LocalizedError {
    case noActiveWorkout
    case startFailed(String)
    case syncFailed(String)
    case autofillFailed(String)
    case invalidResponse
    
    var errorDescription: String? {
        switch self {
        case .noActiveWorkout:
            return "No active workout"
        case .startFailed(let msg):
            return "Failed to start workout: \(msg)"
        case .syncFailed(let msg):
            return "Sync failed: \(msg)"
        case .autofillFailed(let msg):
            return "Autofill failed: \(msg)"
        case .invalidResponse:
            return "Invalid response from server"
        }
    }
}

// MARK: - Idempotency Helper

class IdempotencyKeyHelper {
    static let shared = IdempotencyKeyHelper()
    
    private init() {}
    
    func generate(context: String, exerciseId: String? = nil, setId: String? = nil, field: String? = nil) -> String {
        let components = [context, exerciseId, setId, field].compactMap { $0 }
        let timestamp = Int(Date().timeIntervalSince1970 * 1000)
        return "\(components.joined(separator: "-"))-\(timestamp)"
    }
}

// MARK: - Date Parsing Helper

/// Parse ISO8601 date strings from server (supports multiple formats)
private func parseISO8601Date(_ string: String?) -> Date? {
    guard let string = string else { return nil }
    
    // Try standard ISO8601 formatter first
    let iso8601 = ISO8601DateFormatter()
    iso8601.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    if let date = iso8601.date(from: string) {
        return date
    }
    
    // Try without fractional seconds
    iso8601.formatOptions = [.withInternetDateTime]
    if let date = iso8601.date(from: string) {
        return date
    }
    
    // Try Firebase timestamp format (common alternative)
    let dateFormatter = DateFormatter()
    dateFormatter.locale = Locale(identifier: "en_US_POSIX")
    dateFormatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss.SSSZ"
    if let date = dateFormatter.date(from: string) {
        return date
    }
    
    return nil
}
