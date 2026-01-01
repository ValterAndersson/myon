import Foundation
import OSLog
import UIKit

// =============================================================================
// MARK: - DebugLogger.swift - Comprehensive Session Logging
// =============================================================================
//
// PURPOSE:
// Verbose console logging designed for debugging agent interactions.
// When you copy Xcode logs and paste to an LLM, it can understand:
// - Session context (user, canvas, device)
// - HTTP request/response with full bodies
// - SSE events with full payloads
// - Canvas state snapshots
// - Agent routing decisions
// - Tool calls with arguments and results
// - Timing for all operations
// - Error context
//
// USAGE:
// - SessionLogger.shared.startSession(userId:canvasId:) - Start session tracking
// - SessionLogger.shared.logHTTP(...) - Log HTTP request/response
// - SessionLogger.shared.logSSE(...) - Log SSE event
// - SessionLogger.shared.logCanvasSnapshot(...) - Log canvas state
// - SessionLogger.shared.logError(...) - Log error with context
//
// =============================================================================

// MARK: - Log Categories

enum LogCategory: String {
    case app = "App"
    case network = "Network"
    case canvas = "Canvas"
    case agent = "Agent"
    case auth = "Auth"
    case sse = "SSE"
    case http = "HTTP"
    case firestore = "Firestore"
    case focusMode = "FocusMode"
}

enum LogLevel: String {
    case debug = "DEBUG"
    case info = "INFO"
    case warning = "WARN"
    case error = "ERROR"
}

// MARK: - Session Context

struct SessionContext {
    var userId: String?
    var canvasId: String?
    var sessionId: String?
    var correlationId: String?
    var startTime: Date = Date()
    
    var deviceInfo: String {
        let device = UIDevice.current
        return "\(device.model) / \(device.systemName) \(device.systemVersion)"
    }
}

// MARK: - Legacy DebugLogger (for backward compatibility)

struct DebugLogger {
    private static let subsystem = "com.povver.app"
    private static let toggleKey = "debug_logging_enabled"
    private static let verboseKey = "debug_verbose_enabled"

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
    
    private static var _verbose: Bool = {
        if let stored = UserDefaults.standard.object(forKey: verboseKey) as? Bool {
            return stored
        }
        #if DEBUG
        return true  // Always verbose in debug
        #else
        return false
        #endif
    }()

    static var enabled: Bool { _enabled }
    static var verbose: Bool { _verbose }

    static func setEnabled(_ on: Bool) {
        _enabled = on
        UserDefaults.standard.set(on, forKey: toggleKey)
    }
    
    static func setVerbose(_ on: Bool) {
        _verbose = on
        UserDefaults.standard.set(on, forKey: verboseKey)
    }

    static func log(_ category: LogCategory, _ message: String) {
        guard _enabled else { return }
        let timestamp = SessionLogger.shared.timestamp()
        print("[\(timestamp)] [\(category.rawValue)] \(message)")
        Logger(subsystem: subsystem, category: category.rawValue).info("\(message, privacy: .public)")
    }

    static func error(_ category: LogCategory, _ message: String) {
        guard _enabled else { return }
        let timestamp = SessionLogger.shared.timestamp()
        print("[\(timestamp)] ❌ [\(category.rawValue)] \(message)")
        Logger(subsystem: subsystem, category: category.rawValue).error("\(message, privacy: .public)")
    }

    static func debug(_ category: LogCategory, _ message: String) {
        guard _enabled && _verbose else { return }
        let timestamp = SessionLogger.shared.timestamp()
        print("[\(timestamp)] 🔍 [\(category.rawValue)] \(message)")
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

// MARK: - SessionLogger (New Comprehensive Logger)

final class SessionLogger {
    static let shared = SessionLogger()
    
    private var context = SessionContext()
    private let dateFormatter: DateFormatter = {
        let df = DateFormatter()
        df.dateFormat = "HH:mm:ss.SSS"
        return df
    }()
    private let isoFormatter = ISO8601DateFormatter()
    
    private init() {
        isoFormatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    }
    
    // MARK: - Session Management
    
    func startSession(userId: String, canvasId: String? = nil, sessionId: String? = nil) {
        context = SessionContext()
        context.userId = userId
        context.canvasId = canvasId
        context.sessionId = sessionId
        
        printSessionHeader()
    }
    
    func updateContext(canvasId: String? = nil, sessionId: String? = nil, correlationId: String? = nil) {
        if let c = canvasId { context.canvasId = c }
        if let s = sessionId { context.sessionId = s }
        if let corr = correlationId { context.correlationId = corr }
    }
    
    func endSession() {
        let duration = Date().timeIntervalSince(context.startTime)
        printSessionFooter(duration: duration)
        context = SessionContext()
    }
    
    // MARK: - Timestamp
    
    func timestamp() -> String {
        dateFormatter.string(from: Date())
    }
    
    private func elapsed() -> String {
        let secs = Date().timeIntervalSince(context.startTime)
        return String(format: "+%.2fs", secs)
    }
    
    // MARK: - Session Header/Footer
    
    private func printSessionHeader() {
        let header = """
        
        ╔══════════════════════════════════════════════════════════════════════════════════════════════════════════════════╗
        ║ 🚀 SESSION START                                                                                                  ║
        ╠══════════════════════════════════════════════════════════════════════════════════════════════════════════════════╣
        ║ User:    \(pad(context.userId ?? "unknown", 100))║
        ║ Canvas:  \(pad(context.canvasId ?? "pending", 100))║
        ║ Session: \(pad(context.sessionId ?? "pending", 100))║
        ║ Device:  \(pad(context.deviceInfo, 100))║
        ║ Time:    \(pad(isoFormatter.string(from: context.startTime), 100))║
        ╚══════════════════════════════════════════════════════════════════════════════════════════════════════════════════╝
        
        """
        print(header)
    }
    
    private func printSessionFooter(duration: TimeInterval) {
        let footer = """
        
        ╔══════════════════════════════════════════════════════════════════════════════════════════════════════════════════╗
        ║ 🏁 SESSION END                                                                                                    ║
        ╠══════════════════════════════════════════════════════════════════════════════════════════════════════════════════╣
        ║ Duration: \(pad(String(format: "%.2fs", duration), 98))║
        ║ User:     \(pad(context.userId ?? "unknown", 98))║
        ║ Canvas:   \(pad(context.canvasId ?? "unknown", 98))║
        ╚══════════════════════════════════════════════════════════════════════════════════════════════════════════════════╝
        
        """
        print(footer)
    }
    
    private func pad(_ s: String, _ width: Int) -> String {
        if s.count >= width { return String(s.prefix(width)) }
        return s + String(repeating: " ", count: width - s.count)
    }
    
    // MARK: - HTTP Logging
    
    func logHTTPRequest(
        method: String,
        endpoint: String,
        headers: [String: String]? = nil,
        body: Any? = nil
    ) {
        guard DebugLogger.enabled else { return }
        
        var output = """
        
        [\(timestamp())] 📤 HTTP REQUEST
          \(method) \(endpoint)
        """
        
        if DebugLogger.verbose, let headers = headers {
            let sanitized = DebugLogger.sanitizeHeaders(headers)
            output += "\n  Headers: \(formatJSON(sanitized))"
        }
        
        if let body = body {
            output += "\n  Body: \(formatJSON(body))"
        }
        
        print(output)
    }
    
    func logHTTPResponse(
        method: String,
        endpoint: String,
        statusCode: Int,
        durationMs: Int,
        body: Any? = nil,
        error: Error? = nil
    ) {
        guard DebugLogger.enabled else { return }
        
        let statusEmoji = statusCode >= 200 && statusCode < 300 ? "✅" : "❌"
        
        var output = """
        
        [\(timestamp())] 📥 HTTP RESPONSE (\(durationMs)ms) \(statusEmoji) \(statusCode)
          \(method) \(endpoint)
        """
        
        if let body = body {
            output += "\n  Body: \(formatJSON(body))"
        }
        
        if let error = error {
            output += "\n  Error: \(error.localizedDescription)"
        }
        
        print(output)
    }
    
    // MARK: - SSE Logging
    
    func logSSEStreamStart(
        endpoint: String,
        correlationId: String,
        message: String,
        sessionId: String? = nil
    ) {
        guard DebugLogger.enabled else { return }
        
        context.correlationId = correlationId
        
        let output = """
        
        [\(timestamp())] 📡 SSE STREAM START
          Endpoint: \(endpoint)
          Correlation: \(correlationId)
          Session: \(sessionId ?? "nil")
          Message: "\(message)"
        
        """
        print(output)
    }
    
    func logSSEEvent(type: String, content: [String: Any]?, agent: String? = nil, metadata: [String: Any]? = nil) {
        guard DebugLogger.enabled else { return }
        
        let emoji = sseEventEmoji(type)
        
        var output = "[\(timestamp())] \(emoji) SSE: \(type.uppercased())"
        
        if let agent = agent {
            output += " (agent: \(agent))"
        }
        
        if DebugLogger.verbose {
            if let content = content, !content.isEmpty {
                output += "\n  Content: \(formatJSON(content))"
            }
            if let metadata = metadata, !metadata.isEmpty {
                output += "\n  Metadata: \(formatJSON(metadata))"
            }
        } else {
            // Compact mode: show key info only
            if let content = content {
                if let tool = content["tool"] as? String ?? content["tool_name"] as? String {
                    output += " tool=\(tool)"
                }
                if let text = content["text"] as? String, !text.isEmpty {
                    let preview = String(text.prefix(80))
                    output += " text=\"\(preview)\(text.count > 80 ? "..." : "")\""
                }
                if let phase = content["phase"] as? String {
                    output += " phase=\(phase)"
                }
            }
        }
        
        print(output)
    }
    
    func logSSEStreamEnd(eventCount: Int, durationMs: Int) {
        guard DebugLogger.enabled else { return }
        
        let output = """
        
        [\(timestamp())] 🏁 SSE STREAM END
          Events: \(eventCount)
          Duration: \(durationMs)ms
        
        """
        print(output)
    }
    
    private func sseEventEmoji(_ type: String) -> String {
        switch type.lowercased() {
        case "thinking": return "🧠"
        case "thought": return "💭"
        case "toolrunning", "tool_running", "tool_started": return "⚙️"
        case "toolcomplete", "tool_complete", "tool_result": return "✅"
        case "message", "text_delta": return "💬"
        case "agentresponse", "agent_response": return "🤖"
        case "status": return "📊"
        case "error": return "❌"
        case "done": return "🏁"
        case "routing", "route": return "🔀"
        case "clarification_request": return "❓"
        case "heartbeat", "ping": return "💓"
        case "user_prompt": return "👤"
        case "user_response": return "👤"
        default: return "📌"
        }
    }
    
    // MARK: - Agent Routing
    
    func logAgentRouting(agent: String, intent: String? = nil, confidence: Double? = nil, reason: String? = nil) {
        guard DebugLogger.enabled else { return }
        
        let agentEmoji: String
        switch agent.lowercased() {
        case "coach", "coachagent": agentEmoji = "🎓"
        case "planner", "planneragent": agentEmoji = "📋"
        case "copilot", "copilotagent": agentEmoji = "🚀"
        case "analysis", "analysisagent": agentEmoji = "📊"
        default: agentEmoji = "🤖"
        }
        
        var output = """
        
        [\(timestamp())] 🔀 AGENT ROUTING
          Agent: \(agentEmoji) \(agent)
        """
        
        if let intent = intent {
            output += "\n  Intent: \(intent)"
        }
        if let confidence = confidence {
            output += "\n  Confidence: \(String(format: "%.2f", confidence))"
        }
        if let reason = reason {
            output += "\n  Reason: \(reason)"
        }
        
        print(output)
    }
    
    // MARK: - Canvas State Snapshots
    
    func logCanvasSnapshot(
        phase: String,
        version: Int,
        cards: [(id: String, type: String, status: String, title: String?)],
        upNext: [String],
        trigger: String = "update"
    ) {
        guard DebugLogger.enabled else { return }
        
        var output = """
        
        [\(timestamp())] 🔄 CANVAS SNAPSHOT (\(trigger))
          Phase: \(phase)
          Version: \(version)
          Cards (\(cards.count)):
        """
        
        for (index, card) in cards.enumerated() {
            let title = card.title != nil ? " - \"\(card.title!)\"" : ""
            output += "\n    [\(index)] \(card.type) (\(card.status)) id=\(card.id)\(title)"
        }
        
        output += "\n  UpNext: [\(upNext.joined(separator: ", "))]"
        
        print(output)
    }
    
    func logCanvasAction(type: String, cardId: String?, payload: [String: Any]?, expectedVersion: Int) {
        guard DebugLogger.enabled else { return }
        
        var output = """
        
        [\(timestamp())] ⚡ CANVAS ACTION
          Type: \(type)
          Card: \(cardId ?? "nil")
          Expected Version: \(expectedVersion)
        """
        
        if DebugLogger.verbose, let payload = payload, !payload.isEmpty {
            output += "\n  Payload: \(formatJSON(payload))"
        }
        
        print(output)
    }
    
    // MARK: - Focus Mode Logging
    
    /// Log workout session lifecycle
    func logFocusModeSession(
        event: FocusModeSessionEvent,
        workoutId: String,
        sessionId: String? = nil,
        details: [String: Any]? = nil
    ) {
        guard DebugLogger.enabled else { return }
        
        let emoji = event.emoji
        let eventName = event.rawValue.uppercased()
        
        var output = "[\(timestamp())] \(emoji) [FocusMode] \(eventName) workout=\(workoutId.prefix(8))..."
        
        if let sessionId = sessionId {
            output += " session=\(sessionId.prefix(8))..."
        }
        
        if DebugLogger.verbose, let details = details, !details.isEmpty {
            output += "\n  Details: \(formatJSON(details))"
        }
        
        print(output)
    }
    
    /// Log mutation operations
    func logFocusModeMutation(
        phase: MutationPhase,
        type: String,
        exerciseId: String? = nil,
        setId: String? = nil,
        details: [String: Any]? = nil,
        error: Error? = nil
    ) {
        guard DebugLogger.enabled else { return }
        
        let emoji = phase.emoji
        let phaseName = phase.rawValue
        
        var output = "[\(timestamp())] \(emoji) [FocusMode] \(type) (\(phaseName))"
        
        if let exId = exerciseId {
            output += " exercise=\(exId.prefix(8))..."
        }
        if let sId = setId {
            output += " set=\(sId.prefix(8))..."
        }
        
        if let error = error {
            output += " error=\"\(error.localizedDescription)\""
        }
        
        if DebugLogger.verbose, let details = details, !details.isEmpty {
            output += "\n  \(formatJSON(details))"
        }
        
        print(output)
    }
    
    /// Log coordinator state changes
    func logFocusModeCoordinator(
        event: CoordinatorEvent,
        pending: Int = 0,
        inFlight: String? = nil,
        context: [String: Any]? = nil
    ) {
        guard DebugLogger.enabled else { return }
        
        let emoji = event.emoji
        
        var output = "[\(timestamp())] \(emoji) [Coordinator] \(event.rawValue)"
        
        if pending > 0 {
            output += " pending=\(pending)"
        }
        if let mutation = inFlight {
            output += " inFlight=\(mutation)"
        }
        
        if DebugLogger.verbose, let context = context, !context.isEmpty {
            output += "\n  \(formatJSON(context))"
        }
        
        print(output)
    }
    
    // MARK: - Firestore Logging
    
    func logFirestoreSnapshot(collection: String, documentCount: Int, source: String) {
        guard DebugLogger.enabled && DebugLogger.verbose else { return }
        
        let output = "[\(timestamp())] 🔥 FIRESTORE: \(collection) (\(documentCount) docs, source: \(source))"
        print(output)
    }
    
    func logFirestoreWrite(collection: String, documentId: String, operation: String) {
        guard DebugLogger.enabled else { return }
        
        let output = "[\(timestamp())] 🔥 FIRESTORE WRITE: \(operation) \(collection)/\(documentId)"
        print(output)
    }
    
    // MARK: - Error Logging
    
    func logError(
        category: LogCategory,
        message: String,
        error: Error? = nil,
        context: [String: Any]? = nil
    ) {
        let output = """
        
        ╔══════════════════════════════════════════════════════════════════════════════════════════════════════════════════╗
        ║ ❌ ERROR                                                                                                          ║
        ╠══════════════════════════════════════════════════════════════════════════════════════════════════════════════════╣
        ║ Time:     \(pad(timestamp(), 98))║
        ║ Category: \(pad(category.rawValue, 98))║
        ║ Message:  \(pad(message, 98))║
        \(error != nil ? "║ Error:    \(pad(error!.localizedDescription, 98))║\n" : "")╠══════════════════════════════════════════════════════════════════════════════════════════════════════════════════╣
        ║ Session Context:                                                                                                  ║
        ║   User:        \(pad(self.context.userId ?? "unknown", 94))║
        ║   Canvas:      \(pad(self.context.canvasId ?? "unknown", 94))║
        ║   Session:     \(pad(self.context.sessionId ?? "unknown", 94))║
        ║   Correlation: \(pad(self.context.correlationId ?? "unknown", 94))║
        ╚══════════════════════════════════════════════════════════════════════════════════════════════════════════════════╝
        
        """
        print(output)
        
        if DebugLogger.verbose, let context = context {
            print("  Error Context: \(formatJSON(context))")
        }
    }
    
    // MARK: - Tool Call Logging
    
    func logToolCall(
        tool: String,
        args: [String: Any]?,
        phase: String? = nil
    ) {
        guard DebugLogger.enabled else { return }
        
        var output = "[\(timestamp())] ⚙️ TOOL CALL: \(tool)"
        
        if let phase = phase {
            output += " (phase: \(phase))"
        }
        
        if DebugLogger.verbose, let args = args {
            // Redact sensitive args
            var sanitized = args
            for key in ["userId", "user_id"] {
                if sanitized[key] != nil {
                    sanitized[key] = "<user_id>"
                }
            }
            output += "\n  Args: \(formatJSON(sanitized))"
        }
        
        print(output)
    }
    
    func logToolResult(
        tool: String,
        durationMs: Int,
        result: Any?,
        error: Error? = nil
    ) {
        guard DebugLogger.enabled else { return }
        
        let emoji = error == nil ? "✅" : "❌"
        
        var output = "[\(timestamp())] \(emoji) TOOL RESULT: \(tool) (\(durationMs)ms)"
        
        if let error = error {
            output += "\n  Error: \(error.localizedDescription)"
        } else if DebugLogger.verbose, let result = result {
            output += "\n  Result: \(formatJSON(result))"
        }
        
        print(output)
    }
    
    // MARK: - Generic Logging
    
    func log(_ category: LogCategory, _ level: LogLevel, _ message: String, context: [String: Any]? = nil) {
        guard DebugLogger.enabled else { return }
        if level == .debug && !DebugLogger.verbose { return }
        
        let emoji: String
        switch level {
        case .debug: emoji = "🔍"
        case .info: emoji = "ℹ️"
        case .warning: emoji = "⚠️"
        case .error: emoji = "❌"
        }
        
        var output = "[\(timestamp())] \(emoji) [\(category.rawValue)] \(message)"
        
        if DebugLogger.verbose, let context = context, !context.isEmpty {
            output += " | \(formatJSON(context))"
        }
        
        print(output)
    }
    
    // MARK: - JSON Formatting
    
    func formatJSON(_ value: Any) -> String {
        if let encodable = value as? Encodable {
            return formatEncodable(encodable)
        }
        
        if let dict = value as? [String: Any] {
            return formatDictionary(dict)
        }
        
        if let array = value as? [Any] {
            return formatArray(array)
        }
        
        return String(describing: value)
    }
    
    private func formatEncodable<T: Encodable>(_ value: T) -> String {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        encoder.dateEncodingStrategy = .iso8601
        if let data = try? encoder.encode(value), let s = String(data: data, encoding: .utf8) {
            return indentJSON(s)
        }
        return String(describing: value)
    }
    
    private func formatDictionary(_ dict: [String: Any]) -> String {
        guard JSONSerialization.isValidJSONObject(dict) else {
            return String(describing: dict)
        }
        if let data = try? JSONSerialization.data(withJSONObject: dict, options: [.prettyPrinted, .sortedKeys]),
           let s = String(data: data, encoding: .utf8) {
            return indentJSON(s)
        }
        return String(describing: dict)
    }
    
    private func formatArray(_ array: [Any]) -> String {
        guard JSONSerialization.isValidJSONObject(array) else {
            return String(describing: array)
        }
        if let data = try? JSONSerialization.data(withJSONObject: array, options: [.prettyPrinted, .sortedKeys]),
           let s = String(data: data, encoding: .utf8) {
            return indentJSON(s)
        }
        return String(describing: array)
    }
    
    private func indentJSON(_ json: String) -> String {
        // Add proper indentation for nested JSON in logs
        let lines = json.components(separatedBy: "\n")
        if lines.count == 1 { return json }
        return lines.enumerated().map { index, line in
            index == 0 ? line : "    \(line)"
        }.joined(separator: "\n")
    }
}

// MARK: - AgentEventLogger (Legacy - for backward compatibility)

/// Structured logger for agent SSE events - now delegates to SessionLogger
struct AgentEventLogger {
    private static var sessionStartTime: Date?
    private static var eventCounter = 0
    
    static func startSession(canvasId: String, correlationId: String) {
        sessionStartTime = Date()
        eventCounter = 0
        SessionLogger.shared.logSSEStreamStart(
            endpoint: "/streamAgentNormalized",
            correlationId: correlationId,
            message: "(see previous log)",
            sessionId: nil
        )
    }
    
    static func logEvent(_ event: StreamEvent) {
        eventCounter += 1
        
        var contentDict: [String: Any] = [:]
        if let content = event.content {
            for (key, value) in content {
                contentDict[key] = value.value
            }
        }
        
        var metaDict: [String: Any] = [:]
        if let meta = event.metadata {
            for (key, value) in meta {
                metaDict[key] = value.value
            }
        }
        
        SessionLogger.shared.logSSEEvent(
            type: event.type,
            content: contentDict.isEmpty ? nil : contentDict,
            agent: event.agent,
            metadata: metaDict.isEmpty ? nil : metaDict
        )
    }
    
    static func logRouting(to agent: String, confidence: String? = nil, reason: String? = nil) {
        SessionLogger.shared.logAgentRouting(
            agent: agent,
            confidence: confidence != nil ? Double(confidence!) : nil,
            reason: reason
        )
    }
    
    static func endSession(eventCount: Int? = nil) {
        let duration = sessionStartTime.map { Int(Date().timeIntervalSince($0) * 1000) } ?? 0
        SessionLogger.shared.logSSEStreamEnd(
            eventCount: eventCount ?? eventCounter,
            durationMs: duration
        )
        sessionStartTime = nil
        eventCounter = 0
    }
    
    static func logError(_ error: Error) {
        SessionLogger.shared.logError(
            category: .sse,
            message: "SSE Stream Error",
            error: error
        )
    }
}

// MARK: - Focus Mode Event Types

/// Workout session lifecycle events
enum FocusModeSessionEvent: String {
    case started = "workout_started"
    case resumed = "workout_resumed"
    case completed = "workout_completed"
    case cancelled = "workout_cancelled"
    case reset = "session_reset"
    
    var emoji: String {
        switch self {
        case .started: return "🏋️"
        case .resumed: return "▶️"
        case .completed: return "✅"
        case .cancelled: return "🚫"
        case .reset: return "🔄"
        }
    }
}

/// Mutation lifecycle phases
enum MutationPhase: String {
    case optimistic = "optimistic"
    case enqueued = "enqueued"
    case executing = "executing"
    case synced = "synced"
    case failed = "failed"
    case rolledBack = "rolled_back"
    
    var emoji: String {
        switch self {
        case .optimistic: return "⚡"
        case .enqueued: return "📥"
        case .executing: return "🔄"
        case .synced: return "✅"
        case .failed: return "❌"
        case .rolledBack: return "↩️"
        }
    }
}

/// Coordinator state events
enum CoordinatorEvent: String {
    case reset = "reset"
    case enqueue = "enqueue"
    case execute = "execute"
    case ack = "ack"
    case waitingDependency = "waiting_dependency"
    case reconcileStart = "reconcile_start"
    case reconcileComplete = "reconcile_complete"
    case retry = "retry"
    
    var emoji: String {
        switch self {
        case .reset: return "🔄"
        case .enqueue: return "📥"
        case .execute: return "⚙️"
        case .ack: return "✅"
        case .waitingDependency: return "⏳"
        case .reconcileStart: return "🔍"
        case .reconcileComplete: return "✅"
        case .retry: return "🔁"
        }
    }
}

// MARK: - Focus Mode Logger Convenience

/// Convenience wrapper for Focus Mode logging
struct FocusModeLogger {
    static let shared = FocusModeLogger()
    
    private init() {}
    
    // MARK: - Session Logging
    
    func sessionStarted(workoutId: String, sessionId: String, name: String?) {
        SessionLogger.shared.logFocusModeSession(
            event: .started,
            workoutId: workoutId,
            sessionId: sessionId,
            details: name != nil ? ["name": name!] : nil
        )
    }
    
    func sessionCompleted(workoutId: String, archivedId: String) {
        SessionLogger.shared.logFocusModeSession(
            event: .completed,
            workoutId: workoutId,
            details: ["archived_id": archivedId]
        )
    }
    
    func sessionCancelled(workoutId: String) {
        SessionLogger.shared.logFocusModeSession(
            event: .cancelled,
            workoutId: workoutId
        )
    }
    
    func sessionReset(newSessionId: String) {
        SessionLogger.shared.logFocusModeSession(
            event: .reset,
            workoutId: "N/A",
            sessionId: newSessionId
        )
    }
    
    // MARK: - Mutation Logging
    
    func addExercise(phase: MutationPhase, exerciseId: String, name: String, setCount: Int) {
        SessionLogger.shared.logFocusModeMutation(
            phase: phase,
            type: "addExercise",
            exerciseId: exerciseId,
            details: ["name": name, "sets": setCount]
        )
    }
    
    func addSet(phase: MutationPhase, exerciseId: String, setId: String) {
        SessionLogger.shared.logFocusModeMutation(
            phase: phase,
            type: "addSet",
            exerciseId: exerciseId,
            setId: setId
        )
    }
    
    func logSet(phase: MutationPhase, exerciseId: String, setId: String, weight: Double?, reps: Int) {
        SessionLogger.shared.logFocusModeMutation(
            phase: phase,
            type: "logSet",
            exerciseId: exerciseId,
            setId: setId,
            details: ["weight": weight ?? 0, "reps": reps]
        )
    }
    
    func patchField(phase: MutationPhase, exerciseId: String, setId: String, field: String, value: Any) {
        SessionLogger.shared.logFocusModeMutation(
            phase: phase,
            type: "patch:\(field)",
            exerciseId: exerciseId,
            setId: setId,
            details: ["value": "\(value)"]
        )
    }
    
    func mutationFailed(type: String, exerciseId: String?, setId: String?, error: Error) {
        SessionLogger.shared.logFocusModeMutation(
            phase: .failed,
            type: type,
            exerciseId: exerciseId,
            setId: setId,
            error: error
        )
    }
    
    // MARK: - Coordinator Logging
    
    func coordinatorReset(sessionId: String) {
        SessionLogger.shared.logFocusModeCoordinator(
            event: .reset,
            context: ["session_id": sessionId]
        )
    }
    
    func coordinatorEnqueue(mutation: String, pendingCount: Int) {
        SessionLogger.shared.logFocusModeCoordinator(
            event: .enqueue,
            pending: pendingCount,
            context: ["mutation": mutation]
        )
    }
    
    func coordinatorExecute(mutation: String, attempt: Int) {
        SessionLogger.shared.logFocusModeCoordinator(
            event: .execute,
            inFlight: mutation,
            context: ["attempt": attempt]
        )
    }
    
    func coordinatorAck(type: String, entityId: String) {
        SessionLogger.shared.logFocusModeCoordinator(
            event: .ack,
            context: ["type": type, "entity": entityId]
        )
    }
    
    func coordinatorWaiting(pendingCount: Int) {
        SessionLogger.shared.logFocusModeCoordinator(
            event: .waitingDependency,
            pending: pendingCount
        )
    }
    
    func coordinatorReconcileStart() {
        SessionLogger.shared.logFocusModeCoordinator(event: .reconcileStart)
    }
    
    func coordinatorReconcileComplete(exercises: Int, sets: Int) {
        SessionLogger.shared.logFocusModeCoordinator(
            event: .reconcileComplete,
            context: ["exercises": exercises, "sets": sets]
        )
    }
}
