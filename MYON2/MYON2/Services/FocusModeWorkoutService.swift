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

@MainActor
class FocusModeWorkoutService: ObservableObject {
    
    // MARK: - Published State
    
    @Published private(set) var workout: FocusModeWorkout?
    @Published private(set) var isLoading: Bool = false
    @Published private(set) var error: String?
    @Published private(set) var isSyncing: Bool = false
    
    // MARK: - Dependencies
    
    private let apiClient = ApiClient.shared
    private let idempotencyHelper = IdempotencyKeyHelper.shared
    
    // MARK: - Pending Sync Queue
    
    private var pendingSyncOperations: [(request: Any, completion: (Bool) -> Void)] = []
    
    // MARK: - Endpoints
    
    private let baseUrl = StrengthOSConfig.functionsBaseUrl
    
    private var logSetUrl: URL { URL(string: "\(baseUrl)/logSet")! }
    private var patchActiveWorkoutUrl: URL { URL(string: "\(baseUrl)/patchActiveWorkout")! }
    private var autofillExerciseUrl: URL { URL(string: "\(baseUrl)/autofillExercise")! }
    private var startActiveWorkoutUrl: URL { URL(string: "\(baseUrl)/startActiveWorkout")! }
    private var completeActiveWorkoutUrl: URL { URL(string: "\(baseUrl)/completeActiveWorkout")! }
    
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
        
        let body: [String: Any] = [
            "name": name as Any,
            "source_template_id": sourceTemplateId as Any,
            "source_routine_id": sourceRoutineId as Any,
            "exercises": exercises.map { exerciseToDict($0) }
        ].compactMapValues { $0 }
        
        let response: StartWorkoutResponse = try await apiClient.post(
            url: startActiveWorkoutUrl,
            body: body
        )
        
        guard response.success, let workoutDoc = response.activeWorkoutDoc else {
            throw FocusModeError.startFailed(response.error ?? "Unknown error")
        }
        
        // Parse the workout
        let workout = try parseWorkout(from: workoutDoc, workoutId: response.workoutId)
        self.workout = workout
        return workout
    }
    
    /// Load existing active workout (for resume)
    func loadWorkout(workoutId: String) async throws {
        isLoading = true
        defer { isLoading = false }
        
        // TODO: Call getActiveWorkout endpoint
        // For now, this would be a direct Firestore read
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
            let response: LogSetResponse = try await apiClient.post(
                url: logSetUrl,
                body: request
            )
            
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
            DebugLogger.shared.log("logSet sync failed: \(error)", category: .network)
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
        let op = PatchOperation(
            op: "set_field",
            target: PatchOperation.PatchTarget(exerciseInstanceId: exerciseInstanceId, setId: setId),
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
        
        // 2. Build request
        let idempotencyKey = idempotencyHelper.generate(context: "addSet", setId: newSetId)
        
        let addValue: [String: Any] = [
            "id": newSetId,
            "set_type": setType.rawValue,
            "weight": weight as Any,
            "reps": reps,
            "rir": rir as Any,
            "status": "planned"
        ].compactMapValues { $0 }
        
        let op = PatchOperation(
            op: "add_set",
            target: PatchOperation.PatchTarget(exerciseInstanceId: exerciseInstanceId, setId: nil),
            field: nil,
            value: AnyCodable(addValue)
        )
        
        let request = PatchActiveWorkoutRequest(
            workoutId: workout.id,
            ops: [op],
            cause: "user_edit",
            uiSource: "add_set_button",
            idempotencyKey: idempotencyKey,
            clientTimestamp: ISO8601DateFormatter().string(from: Date()),
            aiScope: nil
        )
        
        return try await syncPatch(request)
    }
    
    /// Add a new exercise to the workout
    func addExercise(
        exercise: Exercise,
        withSets initialSets: [FocusModeSet]? = nil
    ) async throws {
        guard var workout = workout else {
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
        
        // Apply optimistically
        workout.exercises.append(newExercise)
        self.workout = workout
        
        // Build request
        let idempotencyKey = idempotencyHelper.generate(context: "addExercise", exerciseId: newInstanceId)
        
        let exerciseValue: [String: Any] = [
            "instance_id": newInstanceId,
            "exercise_id": exercise.id,
            "name": exercise.name,
            "position": newExercise.position,
            "sets": defaultSets.map { [
                "id": $0.id,
                "set_type": $0.setType.rawValue,
                "status": $0.status.rawValue,
                "reps": $0.targetReps ?? 10,
                "rir": $0.targetRir ?? 2
            ] as [String : Any] }
        ]
        
        let op = PatchOperation(
            op: "add_exercise",
            target: PatchOperation.PatchTarget(exerciseInstanceId: newInstanceId, setId: nil),
            field: nil,
            value: AnyCodable(exerciseValue)
        )
        
        let request = PatchActiveWorkoutRequest(
            workoutId: workout.id,
            ops: [op],
            cause: "user_edit",
            uiSource: "add_exercise_button",
            idempotencyKey: idempotencyKey,
            clientTimestamp: ISO8601DateFormatter().string(from: Date()),
            aiScope: nil
        )
        
        _ = try await syncPatch(request)
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
        
        let op = PatchOperation(
            op: "remove_set",
            target: PatchOperation.PatchTarget(exerciseInstanceId: exerciseInstanceId, setId: setId),
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
        
        let response: AutofillExerciseResponse = try await apiClient.post(
            url: autofillExerciseUrl,
            body: request
        )
        
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
    
    private func syncPatch(_ request: PatchActiveWorkoutRequest) async throws -> WorkoutTotals {
        isSyncing = true
        defer { isSyncing = false }
        
        let response: PatchActiveWorkoutResponse = try await apiClient.post(
            url: patchActiveWorkoutUrl,
            body: request
        )
        
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
            workout.exercises[exIdx].sets[setIdx].status = .done
            workout.exercises[exIdx].sets[setIdx].weight = weight
            workout.exercises[exIdx].sets[setIdx].reps = reps
            workout.exercises[exIdx].sets[setIdx].rir = rir
            if let isFailure = isFailure {
                workout.exercises[exIdx].sets[setIdx].tags = FocusModeSetTags(isFailure: isFailure)
            }
            self.workout = workout
        }
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
                    // Update target if planned, actual if done
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
            workout.exercises[exIdx].sets.removeAll { $0.id == setId }
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
            // Apply updates
            for update in updates {
                if let setIdx = workout.exercises[exIdx].sets.firstIndex(where: { $0.id == update.setId }) {
                    if let weight = update.weight { workout.exercises[exIdx].sets[setIdx].targetWeight = weight }
                    if let reps = update.reps { workout.exercises[exIdx].sets[setIdx].targetReps = reps }
                    if let rir = update.rir { workout.exercises[exIdx].sets[setIdx].targetRir = rir }
                }
            }
            
            // Apply additions
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
    
    // MARK: - Parsing Helpers
    
    private func exerciseToDict(_ exercise: FocusModeExercise) -> [String: Any] {
        return [
            "instance_id": exercise.instanceId,
            "exercise_id": exercise.exerciseId,
            "name": exercise.name,
            "position": exercise.position,
            "sets": exercise.sets.map { setToDict($0) }
        ]
    }
    
    private func setToDict(_ set: FocusModeSet) -> [String: Any] {
        var dict: [String: Any] = [
            "id": set.id,
            "set_type": set.setType.rawValue,
            "status": set.status.rawValue
        ]
        if let weight = set.targetWeight { dict["weight"] = weight }
        if let reps = set.targetReps { dict["reps"] = reps }
        if let rir = set.targetRir { dict["rir"] = rir }
        return dict
    }
    
    private func parseWorkout(from doc: [String: Any], workoutId: String) throws -> FocusModeWorkout {
        // Parse exercises
        let exercisesData = doc["exercises"] as? [[String: Any]] ?? []
        let exercises = exercisesData.compactMap { parseExercise(from: $0) }
        
        return FocusModeWorkout(
            id: workoutId,
            userId: doc["user_id"] as? String ?? "",
            status: .inProgress,
            sourceTemplateId: doc["source_template_id"] as? String,
            sourceRoutineId: doc["source_routine_id"] as? String,
            name: doc["name"] as? String,
            exercises: exercises,
            totals: WorkoutTotals(),
            startTime: Date(),
            endTime: nil,
            createdAt: Date(),
            updatedAt: nil
        )
    }
    
    private func parseExercise(from dict: [String: Any]) -> FocusModeExercise? {
        guard let instanceId = dict["instance_id"] as? String,
              let exerciseId = dict["exercise_id"] as? String,
              let name = dict["name"] as? String else {
            return nil
        }
        
        let setsData = dict["sets"] as? [[String: Any]] ?? []
        let sets = setsData.compactMap { parseSet(from: $0) }
        
        return FocusModeExercise(
            instanceId: instanceId,
            exerciseId: exerciseId,
            name: name,
            position: dict["position"] as? Int ?? 0,
            sets: sets
        )
    }
    
    private func parseSet(from dict: [String: Any]) -> FocusModeSet? {
        guard let id = dict["id"] as? String else { return nil }
        
        return FocusModeSet(
            id: id,
            setType: FocusModeSetType(rawValue: dict["set_type"] as? String ?? "working") ?? .working,
            status: FocusModeSetStatus(rawValue: dict["status"] as? String ?? "planned") ?? .planned,
            targetWeight: dict["target_weight"] as? Double ?? dict["weight"] as? Double,
            targetReps: dict["target_reps"] as? Int ?? dict["reps"] as? Int,
            targetRir: dict["target_rir"] as? Int ?? dict["rir"] as? Int,
            weight: dict["weight"] as? Double,
            reps: dict["reps"] as? Int,
            rir: dict["rir"] as? Int
        )
    }
}

// MARK: - Response Types

private struct StartWorkoutResponse: Decodable {
    let success: Bool
    let workoutId: String
    let activeWorkoutDoc: [String: Any]?
    let error: String?
    
    enum CodingKeys: String, CodingKey {
        case success
        case workoutId = "workout_id"
        case activeWorkoutDoc = "active_workout_doc"
        case error
    }
    
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        success = (try? container.decode(Bool.self, forKey: .success)) ?? false
        workoutId = (try? container.decode(String.self, forKey: .workoutId)) ?? ""
        error = try? container.decode(String.self, forKey: .error)
        
        // Parse activeWorkoutDoc as [String: Any]
        if let docData = try? container.decode([String: AnyCodable].self, forKey: .activeWorkoutDoc) {
            activeWorkoutDoc = docData.mapValues { $0.value }
        } else {
            activeWorkoutDoc = nil
        }
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
