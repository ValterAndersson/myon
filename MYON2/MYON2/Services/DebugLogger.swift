import Foundation
import OSLog

enum LogCategory: String {
    case app = "App"
    case network = "Network"
    case canvas = "Canvas"
    case agent = "Agent"
    case auth = "Auth"
}

struct DebugLogger {
    private static let subsystem = "com.myon.app"
    private static let toggleKey = "debug_logging_enabled"

    private static var _enabled: Bool = {
        if let stored = UserDefaults.standard.object(forKey: toggleKey) as? Bool {
            return stored
        }
        #if DEBUG
        return true
        #else
        return false
        #endif
    }()

    static var enabled: Bool { _enabled }

    static func setEnabled(_ on: Bool) {
        _enabled = on
        UserDefaults.standard.set(on, forKey: toggleKey)
    }

    static func log(_ category: LogCategory, _ message: String) {
        guard _enabled else { return }
        Logger(subsystem: subsystem, category: category.rawValue).info("\(message, privacy: .public)")
    }

    static func error(_ category: LogCategory, _ message: String) {
        guard _enabled else { return }
        Logger(subsystem: subsystem, category: category.rawValue).error("\(message, privacy: .public)")
    }

    static func debug(_ category: LogCategory, _ message: String) {
        guard _enabled else { return }
        Logger(subsystem: subsystem, category: category.rawValue).debug("\(message, privacy: .public)")
    }

    static func sanitizeHeaders(_ headers: [String: String]) -> [String: String] {
        var copy = headers
        let redact = "<redacted>"
        let sensitive = ["Authorization", "authorization", "X-API-Key", "x-api-key"]
        for key in sensitive { if copy[key] != nil { copy[key] = redact } }
        return copy
    }

    static func prettyJSON<T: Encodable>(_ value: T) -> String {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        encoder.dateEncodingStrategy = .iso8601
        if let data = try? encoder.encode(value), let s = String(data: data, encoding: .utf8) { return s }
        return String(describing: value)
    }
}


