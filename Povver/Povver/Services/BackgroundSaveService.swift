import Foundation

/// Manages background save operations with observable sync state per entity.
/// Views submit long-running saves (upsertWorkout, patchTemplate, patchRoutine) and dismiss
/// immediately. The service runs the operation asynchronously and publishes state changes
/// so list rows and detail views can show syncing/error indicators.
@MainActor
class BackgroundSaveService: ObservableObject {
    static let shared = BackgroundSaveService()

    @Published private(set) var pendingSaves: [String: PendingSave] = [:]

    struct PendingSave {
        let entityId: String
        var state: FocusModeSyncState
        let operation: () async throws -> Void
    }

    private init() {}

    /// Submit a background save. Returns immediately.
    /// If a save is already in flight for this entity, the new call is ignored.
    func save(
        entityId: String,
        operation: @escaping () async throws -> Void
    ) {
        guard pendingSaves[entityId] == nil else { return }

        pendingSaves[entityId] = PendingSave(
            entityId: entityId,
            state: .pending,
            operation: operation
        )

        Task {
            do {
                try await operation()
                pendingSaves.removeValue(forKey: entityId)
            } catch {
                pendingSaves[entityId]?.state = .failed(error.localizedDescription)
            }
        }
    }

    /// Retry a failed save.
    func retry(entityId: String) {
        guard let pending = pendingSaves[entityId],
              pending.state.isFailed else { return }

        pendingSaves[entityId]?.state = .pending
        let operation = pending.operation

        Task {
            do {
                try await operation()
                pendingSaves.removeValue(forKey: entityId)
            } catch {
                pendingSaves[entityId]?.state = .failed(error.localizedDescription)
            }
        }
    }

    /// Dismiss a failed save error.
    func dismiss(entityId: String) {
        pendingSaves.removeValue(forKey: entityId)
    }

    /// Check if an entity has a pending or failed save.
    func isSaving(_ entityId: String) -> Bool {
        pendingSaves[entityId] != nil
    }

    /// Get the sync state for an entity, or nil if no pending save.
    func state(for entityId: String) -> FocusModeSyncState? {
        pendingSaves[entityId]?.state
    }
}
