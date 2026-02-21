import Foundation
import os

// =============================================================================
// MARK: - DebugLogger.swift — Unified iOS Logging System
// =============================================================================
//
// Single logger, one format, every line self-contained and machine-parseable.
//
// OUTPUT FORMAT:
//   #0042 [23:21:53.084] AGENT → stream "Plan a routine" corr=4119
//
// CATEGORIES: APP, HTTP, STORE, AGENT, WORK
// DIRECTIONS: → outgoing, ← response, ✕ error, • info
//
// HTTP correlation: httpReq() returns rid (the seq# of the request line).
//   httpRes(rid:) prints ← #rid to correlate response with request.
//
// Agent indentation: 2-space indent while stream is active (AGENT lines only).
//   HTTP events never indent.
//
// =============================================================================

// MARK: - Categories & Directions

enum Cat: String {
    case app   = "APP  "
    case http  = "HTTP "
    case store = "STORE"
    case agent = "AGENT"
    case work  = "WORK "
}

enum Dir: String {
    case out  = "→"
    case `in` = "←"
    case err  = "✕"
    case info = "•"
}

// MARK: - AppLogger

#if DEBUG

final class AppLogger {
    static let shared = AppLogger()

    private let lock = OSAllocatedUnfairLock<State>(initialState: State())

    private struct State {
        var seq: Int = 0
        var inStream: Bool = false
    }

    private init() {}

    // MARK: - Core

    /// All output goes through emit(). Returns the seq number of the emitted line.
    @discardableResult
    private func emit(_ cat: Cat, _ dir: Dir, _ msg: String, indent: Bool = false) -> Int {
        let (seqNum, isInStream) = lock.withLock { state -> (Int, Bool) in
            state.seq = (state.seq % 9999) + 1
            return (state.seq, state.inStream)
        }
        let seqStr = String(format: "#%04d", seqNum)
        let timestamp = ts()
        // When indented AND inside a stream, replace " → " with "   " (same width)
        let middle: String
        if indent && isInStream {
            middle = "   "
        } else {
            middle = " \(dir.rawValue) "
        }
        print("\(seqStr) [\(timestamp)] \(cat.rawValue)\(middle)\(msg)")
        return seqNum
    }

    // MARK: - HTTP (correlation)

    /// Log an outgoing HTTP request. Returns the rid (seq#) for correlation.
    func httpReq(method: String, endpoint: String, body: Any? = nil) -> Int {
        let ep = truncate(endpoint, max: 40)
        let bodyStr = summarize(body)
        let msg = "\(method) \(ep)\(bodyStr.isEmpty ? "" : " \(bodyStr)")"
        return emit(.http, .out, msg)
    }

    /// Log an HTTP response or error, correlated to a previous request via rid.
    func httpRes(rid: Int, status: Int, ms: Int, endpoint: String, body: Any? = nil, error: Error? = nil) {
        let ep = truncate(endpoint, max: 40)
        let badge = latencyBadge(ms)
        let ridStr = String(format: "#%04d", rid)
        if status >= 400 || error != nil {
            let errMsg = error.map { truncate($0.localizedDescription, max: 80) } ?? ""
            emit(.http, .err, "\(ridStr) \(status) \(ms)ms \(ep)\(errMsg.isEmpty ? "" : " \"\(errMsg)\"")\(badge)")
        } else {
            let bodyStr = summarize(body)
            emit(.http, .in, "\(ridStr) \(status) \(ms)ms \(ep)\(bodyStr.isEmpty ? "" : " \(bodyStr)")\(badge)")
        }
    }

    // MARK: - Navigation & User Actions

    func nav(_ destination: String) {
        emit(.app, .out, truncate(destination, max: 80))
    }

    func user(_ action: String, _ detail: String? = nil) {
        let detailStr = detail.map { " \"\(truncate($0, max: 80))\"" } ?? ""
        emit(.app, .out, "\(action)\(detailStr)")
    }

    // MARK: - Firestore

    func snapshot(_ collection: String, docs: Int, source: String) {
        emit(.store, .in, "\(truncate(collection, max: 40)) \(docs)doc \(source)")
    }

    func write(_ collection: String, op: String, docId: String) {
        emit(.store, .out, "\(op) \(truncate(collection, max: 40))/\(truncate(docId, max: 12))")
    }

    // MARK: - Agent Streaming

    /// Start an agent stream. Auto-closes any unclosed previous stream.
    func streamStart(corr: String, session: String?, message: String) {
        let needsAutoClose = lock.withLock { state -> Bool in
            let was = state.inStream
            state.inStream = true
            return was
        }
        if needsAutoClose {
            emit(.agent, .info, "stream auto-closed (previous not ended)")
        }
        let sessStr = session.map { " sess=\(truncate($0, max: 8))" } ?? ""
        emit(.agent, .out, "stream \"\(truncate(message, max: 80))\" corr=\(truncate(corr, max: 8))\(sessStr)")
    }

    /// End an agent stream normally.
    func streamEnd(ms: Int, lane: String?, tools: Int) {
        lock.withLock { state in
            state.inStream = false
        }
        let secs = String(format: "%.1fs", Double(ms) / 1000.0)
        let laneStr = lane.map { " \($0)" } ?? ""
        emit(.agent, .in, "stream \(secs) \(tools) tools\(laneStr)")
    }

    /// Abort a stream on error (clears inStream, emits ✕ at root level).
    func streamAbort(_ msg: String, ms: Int) {
        lock.withLock { state in
            state.inStream = false
        }
        emit(.agent, .err, "\(truncate(msg, max: 80)) \(ms)ms")
    }

    func pipeline(_ step: String, _ detail: String) {
        emit(.agent, .info, "\(truncate(step, max: 20)): \(truncate(detail, max: 80))", indent: true)
    }

    func toolStart(_ name: String, args: [String: Any]? = nil) {
        let argsStr = formatToolArgs(args)
        emit(.agent, .info, "tool: \(truncate(name, max: 40))\(argsStr)", indent: true)
    }

    func toolDone(_ name: String, ms: Int, result: String? = nil) {
        let resultStr = result.map { " \(truncate($0, max: 80))" } ?? ""
        emit(.agent, .info, "tool✓ \(truncate(name, max: 40))\(resultStr) \(ms)ms", indent: true)
    }

    func toolFail(_ name: String, ms: Int, error: String) {
        emit(.agent, .info, "tool✗ \(truncate(name, max: 40)) \"\(truncate(error, max: 80))\" \(ms)ms", indent: true)
    }

    func agentText(_ preview: String) {
        emit(.agent, .info, "response: \"\(truncate(preview, max: 80))\"", indent: true)
    }

    // MARK: - Workout

    func workout(_ event: String, _ detail: String) {
        emit(.work, .info, "\(event) \(truncate(detail, max: 80))")
    }

    // MARK: - Errors & Info

    func error(_ cat: Cat, _ msg: String, _ err: Error? = nil) {
        let errStr = err.map { " (\(truncate($0.localizedDescription, max: 80)))" } ?? ""
        emit(cat, .err, "\(truncate(msg, max: 80))\(errStr)")
    }

    func info(_ cat: Cat, _ msg: String) {
        emit(cat, .info, truncate(msg, max: 120))
    }

    // MARK: - Private Helpers

    /// Compact JSON summary. Returns "" for nil/empty, "<invalid>" on serialization failure.
    private func summarize(_ json: Any?, max: Int = 120) -> String {
        guard let json else { return "" }
        if let dict = json as? [String: Any], dict.isEmpty { return "" }
        if let arr = json as? [Any], arr.isEmpty { return "" }
        guard JSONSerialization.isValidJSONObject(json) else {
            return truncate(String(describing: json), max: max)
        }
        guard let data = try? JSONSerialization.data(withJSONObject: json, options: [.sortedKeys]),
              let str = String(data: data, encoding: .utf8) else { return "<invalid>" }
        return truncate(str, max: max)
    }

    private func truncate(_ s: String, max: Int) -> String {
        if s.count <= max { return s }
        return String(s.prefix(max)) + "…"
    }

    /// Thread-safe timestamp via Calendar components (no shared DateFormatter).
    private func ts() -> String {
        let now = Date()
        let comps = Calendar.current.dateComponents([.hour, .minute, .second, .nanosecond], from: now)
        let ms = (comps.nanosecond ?? 0) / 1_000_000
        return String(format: "%02d:%02d:%02d.%03d",
                      comps.hour ?? 0, comps.minute ?? 0, comps.second ?? 0, ms)
    }

    /// Latency badge: nothing <3s, 🐢 3-5s, ⚠️SLOW >5s.
    private func latencyBadge(_ ms: Int) -> String {
        switch ms {
        case ..<3000: return ""
        case 3000..<5000: return " 🐢"
        default: return " ⚠️SLOW"
        }
    }

    private func formatToolArgs(_ args: [String: Any]?) -> String {
        guard let args, !args.isEmpty else { return "" }
        let skip = Set(["user_id", "userId", "canvas_id", "canvasId", "correlation_id"])
        var parts: [String] = []
        for (key, value) in args.sorted(by: { $0.key < $1.key }) where !skip.contains(key) {
            if let str = value as? String, !str.isEmpty {
                parts.append("\(key)=\"\(truncate(str, max: 20))\"")
            } else if let num = value as? Int {
                parts.append("\(key)=\(num)")
            } else if let arr = value as? [Any] {
                parts.append("\(key)=[\(arr.count)]")
            }
        }
        if parts.isEmpty { return "" }
        return "(\(parts.prefix(3).joined(separator: ", "))\(parts.count > 3 ? ", …" : ""))"
    }
}

#else

// Release stub — all methods are no-ops, inlined away by compiler
final class AppLogger {
    static let shared = AppLogger()
    @inline(__always) func httpReq(method: String, endpoint: String, body: Any? = nil) -> Int { 0 }
    @inline(__always) func httpRes(rid: Int, status: Int, ms: Int, endpoint: String, body: Any? = nil, error: Error? = nil) {}
    @inline(__always) func nav(_ destination: String) {}
    @inline(__always) func user(_ action: String, _ detail: String? = nil) {}
    @inline(__always) func snapshot(_ collection: String, docs: Int, source: String) {}
    @inline(__always) func write(_ collection: String, op: String, docId: String) {}
    @inline(__always) func streamStart(corr: String, session: String?, message: String) {}
    @inline(__always) func streamEnd(ms: Int, lane: String?, tools: Int) {}
    @inline(__always) func streamAbort(_ msg: String, ms: Int) {}
    @inline(__always) func pipeline(_ step: String, _ detail: String) {}
    @inline(__always) func toolStart(_ name: String, args: [String: Any]? = nil) {}
    @inline(__always) func toolDone(_ name: String, ms: Int, result: String? = nil) {}
    @inline(__always) func toolFail(_ name: String, ms: Int, error: String) {}
    @inline(__always) func agentText(_ preview: String) {}
    @inline(__always) func workout(_ event: String, _ detail: String) {}
    @inline(__always) func error(_ cat: Cat, _ msg: String, _ err: Error? = nil) {}
    @inline(__always) func info(_ cat: Cat, _ msg: String) {}
}

#endif

// MARK: - Focus Mode Event Types

/// Workout session lifecycle events
enum FocusModeSessionEvent: String {
    case started = "workout_started"
    case resumed = "workout_resumed"
    case completed = "workout_completed"
    case cancelled = "workout_cancelled"
    case reset = "session_reset"
}

/// Mutation lifecycle phases
enum MutationPhase: String {
    case optimistic = "optimistic"
    case enqueued = "enqueued"
    case executing = "executing"
    case synced = "synced"
    case failed = "failed"
    case rolledBack = "rolled_back"
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
}

// MARK: - Focus Mode Logger

/// Convenience facade preserving the enum-based API that FocusMode workout code
/// pattern-matches against. All methods delegate to AppLogger.
struct FocusModeLogger {
    static let shared = FocusModeLogger()
    private init() {}

    // MARK: - Session

    func sessionStarted(workoutId: String, sessionId: String, name: String?) {
        AppLogger.shared.workout("started", "id=\(workoutId.prefix(8)) sess=\(sessionId.prefix(8))\(name.map { " \($0)" } ?? "")")
    }

    func sessionCompleted(workoutId: String, archivedId: String) {
        AppLogger.shared.workout("completed", "id=\(workoutId.prefix(8)) archived=\(archivedId.prefix(8))")
    }

    func sessionCancelled(workoutId: String) {
        AppLogger.shared.workout("cancelled", "id=\(workoutId.prefix(8))")
    }

    func sessionReset(newSessionId: String) {
        AppLogger.shared.workout("reset", "sess=\(newSessionId.prefix(8))")
    }

    // MARK: - Mutations

    func addExercise(phase: MutationPhase, exerciseId: String, name: String, setCount: Int) {
        AppLogger.shared.workout("addExercise(\(phase.rawValue))", "ex=\(exerciseId.prefix(8)) \(name) sets=\(setCount)")
    }

    func addSet(phase: MutationPhase, exerciseId: String, setId: String) {
        AppLogger.shared.workout("addSet(\(phase.rawValue))", "ex=\(exerciseId.prefix(8)) set=\(setId.prefix(8))")
    }

    func logSet(phase: MutationPhase, exerciseId: String, setId: String, weight: Double?, reps: Int) {
        let w = weight.map { String(format: "%.1f", $0) } ?? "BW"
        AppLogger.shared.workout("logSet(\(phase.rawValue))", "ex=\(exerciseId.prefix(8)) set=\(setId.prefix(8)) \(w)kg×\(reps)")
    }

    func patchField(phase: MutationPhase, exerciseId: String, setId: String, field: String, value: Any) {
        AppLogger.shared.workout("patch:\(field)(\(phase.rawValue))", "ex=\(exerciseId.prefix(8)) set=\(setId.prefix(8)) =\(value)")
    }

    func mutationFailed(type: String, exerciseId: String?, setId: String?, error: Error) {
        let exStr = exerciseId.map { " ex=\($0.prefix(8))" } ?? ""
        let setStr = setId.map { " set=\($0.prefix(8))" } ?? ""
        AppLogger.shared.error(.work, "\(type) failed\(exStr)\(setStr)", error)
    }

    // MARK: - Coordinator

    func coordinatorReset(sessionId: String) {
        AppLogger.shared.info(.work, "coordinator reset sess=\(sessionId.prefix(8))")
    }

    func coordinatorEnqueue(mutation: String, pendingCount: Int) {
        AppLogger.shared.info(.work, "coordinator enqueue \(mutation) pending=\(pendingCount)")
    }

    func coordinatorExecute(mutation: String, attempt: Int) {
        AppLogger.shared.info(.work, "coordinator execute \(mutation) attempt=\(attempt)")
    }

    func coordinatorAck(type: String, entityId: String) {
        AppLogger.shared.info(.work, "coordinator ack \(type) entity=\(entityId.prefix(8))")
    }

    func coordinatorWaiting(pendingCount: Int) {
        AppLogger.shared.info(.work, "coordinator waiting pending=\(pendingCount)")
    }

    func coordinatorReconcileStart() {
        AppLogger.shared.info(.work, "coordinator reconcile start")
    }

    func coordinatorReconcileComplete(exercises: Int, sets: Int) {
        AppLogger.shared.info(.work, "coordinator reconcile complete ex=\(exercises) sets=\(sets)")
    }
}
