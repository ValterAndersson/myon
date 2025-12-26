import Foundation
import OSLog

enum LogCategory: String {
    case app = "App"
    case network = "Network"
    case canvas = "Canvas"
    case agent = "Agent"
    case auth = "Auth"
    case sse = "SSE"
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

// MARK: - Agent Event Logger

/// Structured logger for agent SSE events - designed for Xcode console debugging
struct AgentEventLogger {
    private static var sessionStartTime: Date?
    private static var eventCounter = 0
    private static var lastEventType: String?
    private static var heartbeatCount = 0
    
    /// Log event types to filter (noise reduction)
    private static let quietTypes = Set(["heartbeat", "ping", "keepalive"])
    
    /// Reset for new session
    static func startSession(canvasId: String, correlationId: String) {
        sessionStartTime = Date()
        eventCounter = 0
        heartbeatCount = 0
        lastEventType = nil
        
        print("""
        
        ╔══════════════════════════════════════════════════════════════╗
        ║  🚀 AGENT SESSION STARTED                                     ║
        ╠══════════════════════════════════════════════════════════════╣
        ║  Canvas: \(canvasId.prefix(20).padding(toLength: 44, withPad: " ", startingAt: 0))║
        ║  Correlation: \(correlationId.prefix(16).padding(toLength: 40, withPad: " ", startingAt: 0))║
        ║  Time: \(ISO8601DateFormatter().string(from: Date()).padding(toLength: 47, withPad: " ", startingAt: 0))║
        ╚══════════════════════════════════════════════════════════════╝
        """)
    }
    
    /// Log SSE event with structured formatting
    static func logEvent(_ event: StreamEvent) {
        let eventType = event.type.lowercased()
        
        // Suppress heartbeat noise - just count them
        if quietTypes.contains(eventType) {
            heartbeatCount += 1
            if heartbeatCount % 10 == 0 {
                print("   💓 [\(heartbeatCount) heartbeats]")
            }
            return
        }
        
        // If we had heartbeats, summarize them
        if heartbeatCount > 0 {
            // Already printed summary above
            heartbeatCount = 0
        }
        
        eventCounter += 1
        let elapsed = sessionStartTime.map { String(format: "%.1fs", Date().timeIntervalSince($0)) } ?? "?"
        
        // Event type icons and formatting
        let (icon, label) = eventTypeInfo(eventType)
        
        print("   \(icon) [\(elapsed)] \(label)")
        
        // Show relevant content based on event type
        logEventContent(event, eventType: eventType)
        
        lastEventType = eventType
    }
    
    private static func eventTypeInfo(_ type: String) -> (icon: String, label: String) {
        switch type {
        case "thinking":
            return ("🧠", "THINKING")
        case "thought":
            return ("💭", "THOUGHT")
        case "tool_running", "tool_started":
            return ("⚙️", "TOOL CALL")
        case "tool_complete", "tool_result":
            return ("✅", "TOOL RESULT")
        case "agent_response", "message":
            return ("💬", "RESPONSE")
        case "cards_proposed", "card_published":
            return ("📋", "CARDS PUBLISHED")
        case "clarification_request":
            return ("❓", "CLARIFICATION")
        case "error":
            return ("❌", "ERROR")
        case "done":
            return ("🏁", "DONE")
        case "status":
            return ("📊", "STATUS")
        case "user_prompt", "user_response":
            return ("👤", "USER")
        default:
            return ("📌", type.uppercased())
        }
    }
    
    private static func logEventContent(_ event: StreamEvent, eventType: String) {
        guard let content = event.content else { return }
        
        switch eventType {
        case "thinking":
            if let text = content["text"]?.value as? String, !text.isEmpty {
                print("      └─ \(text.prefix(100))\(text.count > 100 ? "..." : "")")
            }
            
        case "thought":
            if let duration = content["duration_s"]?.value as? Double {
                print("      └─ Duration: \(String(format: "%.2fs", duration))")
            }
            if let text = content["text"]?.value as? String, !text.isEmpty {
                let preview = text.prefix(80).replacingOccurrences(of: "\n", with: " ")
                print("      └─ \(preview)\(text.count > 80 ? "..." : "")")
            }
            
        case "tool_running", "tool_started":
            let toolName = content["tool"]?.value as? String ?? content["name"]?.value as? String ?? "unknown"
            let humanName = humanReadableToolName(toolName)
            print("      ├─ Tool: \(toolName)")
            print("      └─ Action: \(humanName)")
            // Show args preview
            if let args = content["args"]?.value as? [String: Any] {
                let preview = formatArgs(args)
                if !preview.isEmpty {
                    print("      └─ Args: \(preview)")
                }
            }
            
        case "tool_complete", "tool_result":
            let toolName = content["tool"]?.value as? String ?? content["name"]?.value as? String ?? "unknown"
            let humanName = humanReadableToolResponse(toolName)
            print("      ├─ Tool: \(toolName) → \(humanName)")
            
            // Show result summary
            if let resultCount = content["result_count"]?.value as? Int {
                print("      └─ Found: \(resultCount) items")
            } else if let result = content["result"]?.value as? String {
                let preview = result.prefix(100).replacingOccurrences(of: "\n", with: " ")
                print("      └─ Result: \(preview)\(result.count > 100 ? "..." : "")")
            } else if let summary = content["summary"]?.value as? String {
                print("      └─ Summary: \(summary)")
            }
            // Show duration
            if let duration = content["duration_s"]?.value as? Double {
                print("      └─ Duration: \(String(format: "%.2fs", duration))")
            }
            
        case "agent_response", "message":
            if let text = content["text"]?.value as? String, !text.isEmpty {
                let preview = text.prefix(120).replacingOccurrences(of: "\n", with: " ")
                print("      └─ \(preview)\(text.count > 120 ? "..." : "")")
            }
            
        case "cards_proposed", "card_published":
            if let cards = content["cards"]?.value as? [[String: Any]] {
                print("      └─ Cards: \(cards.count)")
                for (i, card) in cards.prefix(3).enumerated() {
                    let type = card["type"] as? String ?? "?"
                    let title = card["title"] as? String ?? ""
                    print("         [\(i+1)] \(type): \(title.prefix(40))")
                }
                if cards.count > 3 {
                    print("         ... and \(cards.count - 3) more")
                }
            } else if let cardType = content["type"]?.value as? String {
                let title = content["title"]?.value as? String ?? ""
                print("      └─ Card: \(cardType) - \(title.prefix(50))")
            }
            
        case "clarification_request":
            if let question = content["question"]?.value as? String {
                print("      └─ Q: \(question.prefix(80))")
            }
            
        case "error":
            if let msg = content["message"]?.value as? String ?? content["text"]?.value as? String {
                print("      └─ ⚠️ \(msg)")
            }
            
        case "status":
            if let text = content["text"]?.value as? String {
                print("      └─ \(text)")
            }
            
        default:
            // Show first few keys for debugging unknown types
            let keys = content.keys.prefix(5).joined(separator: ", ")
            if !keys.isEmpty {
                print("      └─ Keys: \(keys)")
            }
        }
    }
    
    static func endSession(eventCount: Int? = nil) {
        let elapsed = sessionStartTime.map { String(format: "%.1fs", Date().timeIntervalSince($0)) } ?? "?"
        let count = eventCount ?? eventCounter
        
        print("""
        
        ╔══════════════════════════════════════════════════════════════╗
        ║  🏁 AGENT SESSION ENDED                                       ║
        ╠══════════════════════════════════════════════════════════════╣
        ║  Events: \(String(count).padding(toLength: 48, withPad: " ", startingAt: 0))║
        ║  Duration: \(elapsed.padding(toLength: 46, withPad: " ", startingAt: 0))║
        ╚══════════════════════════════════════════════════════════════╝
        
        """)
    }
    
    static func logError(_ error: Error) {
        print("""
        
        ╔══════════════════════════════════════════════════════════════╗
        ║  ❌ AGENT ERROR                                               ║
        ╠══════════════════════════════════════════════════════════════╣
        ║  \(String(describing: error).prefix(56).padding(toLength: 56, withPad: " ", startingAt: 0))  ║
        ╚══════════════════════════════════════════════════════════════╝
        
        """)
    }
    
    // MARK: - Helpers
    
    private static func formatArgs(_ args: [String: Any]) -> String {
        var parts: [String] = []
        for (key, value) in args.prefix(4) {
            if key == "user_id" || key == "userId" { continue }
            let valueStr = String(describing: value).prefix(30)
            parts.append("\(key)=\(valueStr)")
        }
        return parts.joined(separator: ", ")
    }
    
    private static func humanReadableToolName(_ name: String) -> String {
        switch name {
        case "tool_search_exercises", "search_exercises": return "Searching exercises"
        case "tool_get_user_profile", "get_user": return "Loading profile"
        case "tool_get_recent_workouts", "get_user_workouts": return "Loading workouts"
        case "tool_get_user_templates", "get_user_templates": return "Loading templates"
        case "tool_get_user_routines", "get_user_routines": return "Loading routines"
        case "tool_propose_cards", "propose_cards": return "Publishing cards"
        case "tool_propose_routine", "propose_routine": return "Creating routine"
        case "tool_get_planning_context", "get_planning_context": return "Getting context"
        case "tool_send_message": return "Sending message"
        case "tool_ask_user": return "Asking user"
        default: return name.replacingOccurrences(of: "tool_", with: "").replacingOccurrences(of: "_", with: " ").capitalized
        }
    }
    
    private static func humanReadableToolResponse(_ name: String) -> String {
        switch name {
        case "tool_search_exercises", "search_exercises": return "Exercises found"
        case "tool_get_user_profile", "get_user": return "Profile loaded"
        case "tool_get_recent_workouts", "get_user_workouts": return "Workouts loaded"
        case "tool_get_user_templates", "get_user_templates": return "Templates loaded"
        case "tool_get_user_routines", "get_user_routines": return "Routines loaded"
        case "tool_propose_cards", "propose_cards": return "Cards published"
        case "tool_propose_routine", "propose_routine": return "Routine created"
        case "tool_get_planning_context", "get_planning_context": return "Context loaded"
        default: return "Complete"
        }
    }
}
