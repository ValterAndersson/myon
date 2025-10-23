import Foundation

final class PendingAgentInvoke {
    static let shared = PendingAgentInvoke()
    private let lock = NSLock()
    private var pending: (message: String, correlationId: String)?

    func set(message: String, correlationId: String) {
        lock.lock(); defer { lock.unlock() }
        pending = (message, correlationId)
    }

    func take() -> (message: String, correlationId: String)? {
        lock.lock(); defer { lock.unlock() }
        let v = pending
        pending = nil
        return v
    }
}


