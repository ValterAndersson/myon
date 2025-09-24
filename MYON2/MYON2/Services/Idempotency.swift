import Foundation

actor IdempotencyKeyStore {
    private var recent: [String: Date] = [:]
    private let ttl: TimeInterval
    init(ttl: TimeInterval = 60) { self.ttl = ttl }
    func newKey(prefix: String = "act") -> String { "\(prefix)-\(UUID().uuidString)" }
    func remember(_ key: String) { recent[key] = Date() }
    func seen(_ key: String) -> Bool {
        cleanup(); return recent[key] != nil
    }
    private func cleanup() {
        let now = Date(); recent = recent.filter { now.timeIntervalSince($0.value) < ttl }
    }
}

struct Log {
    static func info(_ message: String) { print("ℹ️  \(message)") }
    static func error(_ message: String) { print("❌  \(message)") }
}


