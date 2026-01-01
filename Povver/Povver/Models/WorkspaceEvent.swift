import Foundation

/// Persisted workspace entry that mirrors a StreamEvent coming from the agent
struct WorkspaceEvent: Identifiable, Equatable {
    let id: String
    let event: StreamEvent
    let createdAt: Date?
    
    static func == (lhs: WorkspaceEvent, rhs: WorkspaceEvent) -> Bool {
        lhs.id == rhs.id
    }
}


