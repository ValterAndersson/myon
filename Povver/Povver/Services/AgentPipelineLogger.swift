import Foundation
import OSLog

// =============================================================================
// MARK: - AgentPipelineLogger.swift - Focused Reasoning Chain Logging
// =============================================================================
//
// PURPOSE:
// Clean, actionable logging for the Shell Agent 4-Lane architecture.
// Designed to show the reasoning chain, not dump raw JSON noise.
//
// DESIGN PRINCIPLES:
// 1. ONE LINE PER STEP - No multi-line JSON dumps
// 2. PIPELINE FOCUS - Router → Planner → Tools → Critic → Response
// 3. TIMING ALWAYS - Every step shows duration
// 4. NO NOISE - Heartbeats, empty events, duplicates suppressed
// 5. ACTIONABLE - When you see it, you can act on it
//
// USAGE:
//   let logger = AgentPipelineLogger()
//   logger.requestStart(correlationId: "...", message: "create PPL routine")
//   logger.routerDecision(lane: .slow, intent: "PLAN_ROUTINE")
//   logger.pipelineStep(.planner, "Use search_exercises, propose_routine")
//   logger.toolStart("search_exercises", args: ["muscle": "chest"])
//   logger.toolComplete("search_exercises", result: "12 exercises", durationMs: 300)
//   logger.requestComplete(totalMs: 5200, toolCount: 2)
//
// =============================================================================

// MARK: - Lane Types (Shell Agent 4-Lane System)

enum AgentLane: String {
    case fast = "FAST"          // Regex match → copilot_skills (no LLM)
    case slow = "SLOW"          // ShellAgent (Pro model)
    case functional = "FUNC"    // FunctionalHandler (Flash model)
    case worker = "WORKER"      // Background PubSub worker
    
    var emoji: String {
        switch self {
        case .fast: return "⚡"
        case .slow: return "🧠"
        case .functional: return "🔧"
        case .worker: return "👷"
        }
    }
    
    var model: String {
        switch self {
        case .fast: return "none"
        case .slow: return "Pro"
        case .functional: return "Flash"
        case .worker: return "Pro"
        }
    }
}

// MARK: - Pipeline Steps (Reasoning Chain)

enum PipelineStep: String {
    case router = "ROUTER"
    case planner = "PLANNER"
    case executor = "EXECUTOR"
    case tool = "TOOL"
    case critic = "CRITIC"
    case safetyGate = "SAFETY"
    case response = "RESPONSE"
    case thinking = "THINKING"
    case error = "ERROR"
    
    var emoji: String {
        switch self {
        case .router: return "🛤️"
        case .planner: return "📋"
        case .executor: return "⚡"
        case .tool: return "⚙️"
        case .critic: return "🔍"
        case .safetyGate: return "🔒"
        case .response: return "🤖"
        case .thinking: return "💭"
        case .error: return "❌"
        }
    }
}

// MARK: - Request State

final class AgentRequestState {
    let correlationId: String
    let canvasId: String?
    let sessionId: String?
    let message: String
    let startTime: Date
    
    var lane: AgentLane?
    var intent: String?
    var toolCount: Int = 0
    var pipelineSteps: [(step: PipelineStep, detail: String, durationMs: Int?)] = []
    var currentToolStart: Date?
    var currentToolName: String?
    var hasError: Bool = false
    
    init(correlationId: String, canvasId: String?, sessionId: String?, message: String) {
        self.correlationId = correlationId
        self.canvasId = canvasId
        self.sessionId = sessionId
        self.message = message
        self.startTime = Date()
    }
    
    var elapsedMs: Int {
        Int(Date().timeIntervalSince(startTime) * 1000)
    }
}

// MARK: - AgentPipelineLogger

final class AgentPipelineLogger {
    static let shared = AgentPipelineLogger()
    
    private var currentRequest: AgentRequestState?
    private let dateFormatter: DateFormatter = {
        let df = DateFormatter()
        df.dateFormat = "HH:mm:ss"
        return df
    }()
    
    private var enabled: Bool {
        #if DEBUG
        return true
        #else
        return false
        #endif
    }
    
    private init() {}
    
    // MARK: - Timestamp
    
    private func ts() -> String {
        dateFormatter.string(from: Date())
    }
    
    private func shortId(_ id: String?) -> String {
        guard let id = id else { return "—" }
        return String(id.prefix(8))
    }
    
    // MARK: - Request Lifecycle
    
    /// Call when SSE stream starts
    func requestStart(correlationId: String, canvasId: String?, sessionId: String?, message: String) {
        guard enabled else { return }
        
        currentRequest = AgentRequestState(
            correlationId: correlationId,
            canvasId: canvasId,
            sessionId: sessionId,
            message: message
        )
        
        let msgPreview = String(message.prefix(60)).replacingOccurrences(of: "\n", with: " ")
        
        print("""
        
        ┌─────────────────────────────────────────────────────────────────────────────────┐
        │ 🚀 AGENT REQUEST                                                                │
        │ corr=\(shortId(correlationId)) • canvas=\(shortId(canvasId)) • session=\(shortId(sessionId))\(String(repeating: " ", count: max(0, 32 - shortId(canvasId).count - shortId(sessionId).count)))│
        │ "\(msgPreview)\(msgPreview.count < message.count ? "..." : "")\(String(repeating: " ", count: max(0, 70 - msgPreview.count)))│
        └─────────────────────────────────────────────────────────────────────────────────┘
        """)
    }
    
    /// Call when routing decision is made (from SSE status or routing event)
    func routerDecision(lane: AgentLane, intent: String?) {
        guard enabled, let req = currentRequest else { return }
        
        req.lane = lane
        req.intent = intent
        
        let intentStr = intent != nil ? " intent=\(intent!)" : ""
        print("[\(ts())] [\(PipelineStep.router.rawValue)] \(lane.emoji) \(lane.rawValue)_LANE (\(lane.model))\(intentStr)")
    }
    
    /// Infer lane from agent name (fallback when no explicit routing event)
    func inferLaneFromAgent(_ agent: String?) {
        guard let agent = agent?.lowercased() else { return }
        
        let lane: AgentLane
        if agent.contains("fast") || agent.contains("copilot") {
            lane = .fast
        } else if agent.contains("functional") || agent.contains("flash") {
            lane = .functional
        } else if agent.contains("worker") || agent.contains("analyst") {
            lane = .worker
        } else {
            lane = .slow // Default to slow lane for orchestrator, coach, planner
        }
        
        if currentRequest?.lane == nil {
            routerDecision(lane: lane, intent: nil)
        }
    }
    
    /// Call for pipeline steps (planner, executor, critic, safety gate)
    func pipelineStep(_ step: PipelineStep, _ detail: String, durationMs: Int? = nil) {
        guard enabled else { return }
        
        currentRequest?.pipelineSteps.append((step, detail, durationMs))
        
        let durationStr = durationMs != nil ? " (\(durationMs!)ms)" : ""
        print("[\(ts())]   ├─ \(step.emoji) \(step.rawValue): \(detail)\(durationStr)")
    }
    
    // MARK: - Tool Tracking
    
    /// Call when tool starts executing
    func toolStart(_ name: String, args: [String: Any]? = nil) {
        guard enabled, let req = currentRequest else { return }
        
        req.currentToolStart = Date()
        req.currentToolName = name
        
        let argsStr = formatToolArgs(args)
        print("[\(ts())]   ├─ \(PipelineStep.tool.emoji) \(humanToolName(name))\(argsStr) ...")
    }
    
    /// Call when tool completes
    func toolComplete(_ name: String, result: String?, durationMs: Int? = nil) {
        guard enabled, let req = currentRequest else { return }
        
        req.toolCount += 1
        
        let duration: Int
        if let d = durationMs {
            duration = d
        } else if let start = req.currentToolStart {
            duration = Int(Date().timeIntervalSince(start) * 1000)
        } else {
            duration = 0
        }
        
        let resultStr = result != nil ? " → \(result!)" : ""
        print("[\(ts())]   │  └─ ✅ \(humanToolName(name))\(resultStr) (\(duration)ms)")
        
        req.currentToolStart = nil
        req.currentToolName = nil
    }
    
    /// Call when tool fails
    func toolFailed(_ name: String, error: String, durationMs: Int? = nil) {
        guard enabled, let req = currentRequest else { return }
        
        req.hasError = true
        
        let duration: Int
        if let d = durationMs {
            duration = d
        } else if let start = req.currentToolStart {
            duration = Int(Date().timeIntervalSince(start) * 1000)
        } else {
            duration = 0
        }
        
        print("[\(ts())]   │  └─ ❌ \(humanToolName(name)): \(error) (\(duration)ms)")
        
        req.currentToolStart = nil
        req.currentToolName = nil
    }
    
    // MARK: - Thinking/Reasoning
    
    /// Call when agent is thinking (optional - suppress in compact mode)
    func thinking(_ text: String? = nil) {
        guard enabled else { return }
        
        if let text = text, !text.isEmpty {
            let preview = String(text.prefix(50))
            print("[\(ts())]   ├─ \(PipelineStep.thinking.emoji) \(preview)\(text.count > 50 ? "..." : "")")
        }
    }
    
    // MARK: - Response
    
    /// Call when agent sends text response
    func responseChunk(_ text: String, isCommit: Bool = false) {
        guard enabled else { return }
        
        // Only log commits or first significant chunk
        if isCommit {
            let preview = String(text.prefix(80)).replacingOccurrences(of: "\n", with: " ")
            print("[\(ts())]   └─ \(PipelineStep.response.emoji) \"\(preview)\(text.count > 80 ? "..." : "")\"")
        }
    }
    
    // MARK: - Request Complete
    
    /// Call when SSE stream ends
    func requestComplete(totalMs: Int? = nil, toolCount: Int? = nil) {
        guard enabled, let req = currentRequest else { return }
        
        let duration = totalMs ?? req.elapsedMs
        let tools = toolCount ?? req.toolCount
        let lane = req.lane ?? .slow
        
        let status = req.hasError ? "❌ ERROR" : "✅ COMPLETE"
        let latencyBadge = categorizeLatency(duration)
        
        print("""
        
        ┌─────────────────────────────────────────────────────────────────────────────────┐
        │ \(status) • \(formatDuration(duration))\(latencyBadge) • \(tools) tool\(tools == 1 ? "" : "s") • lane=\(lane.rawValue)\(String(repeating: " ", count: max(0, 37 - formatDuration(duration).count - lane.rawValue.count)))│
        └─────────────────────────────────────────────────────────────────────────────────┘
        
        """)
        
        currentRequest = nil
    }
    
    /// Call on error
    func requestFailed(error: String, afterMs: Int? = nil) {
        guard enabled, let req = currentRequest else { return }
        
        req.hasError = true
        let duration = afterMs ?? req.elapsedMs
        
        print("""
        
        ┌─────────────────────────────────────────────────────────────────────────────────┐
        │ ❌ FAILED after \(formatDuration(duration))                                                           │
        │ Error: \(String(error.prefix(70)))\(String(repeating: " ", count: max(0, 70 - error.prefix(70).count)))│
        └─────────────────────────────────────────────────────────────────────────────────┘
        
        """)
        
        currentRequest = nil
    }
    
    // MARK: - Helpers
    
    private func formatDuration(_ ms: Int) -> String {
        if ms < 1000 {
            return "\(ms)ms"
        } else {
            return String(format: "%.1fs", Double(ms) / 1000.0)
        }
    }
    
    private func categorizeLatency(_ ms: Int) -> String {
        switch ms {
        case 0..<1000: return " ⚡"
        case 1000..<3000: return ""
        case 3000..<5000: return " 🐢"
        default: return " 🔥🐢 SLOW"
        }
    }
    
    private func formatToolArgs(_ args: [String: Any]?) -> String {
        guard let args = args, !args.isEmpty else { return "" }
        
        // Extract only useful args, skip user_id etc.
        var parts: [String] = []
        let skipKeys = Set(["user_id", "userId", "canvas_id", "canvasId", "correlation_id"])
        
        for (key, value) in args where !skipKeys.contains(key) {
            if let str = value as? String, !str.isEmpty {
                let shortVal = String(str.prefix(20))
                parts.append("\(key)=\"\(shortVal)\(str.count > 20 ? "..." : "")\"")
            } else if let num = value as? Int {
                parts.append("\(key)=\(num)")
            } else if let arr = value as? [Any] {
                parts.append("\(key)=[\(arr.count)]")
            }
        }
        
        if parts.isEmpty { return "" }
        return "(\(parts.prefix(3).joined(separator: ", "))\(parts.count > 3 ? ", ..." : ""))"
    }
    
    private func humanToolName(_ name: String) -> String {
        switch name {
        case "get_planning_context": return "LoadContext"
        case "get_training_context": return "LoadTraining"
        case "search_exercises": return "SearchExercises"
        case "get_user_templates": return "LoadTemplates"
        case "get_user_routines": return "LoadRoutines"
        case "get_user_workouts": return "LoadWorkouts"
        case "get_analytics_features": return "LoadAnalytics"
        case "propose_workout", "propose_session": return "ProposeWorkout"
        case "propose_routine": return "ProposeRoutine"
        case "start_active_workout": return "StartWorkout"
        case "log_set": return "LogSet"
        case "swap_exercise": return "SwapExercise"
        case "add_exercise": return "AddExercise"
        default: return name.split(separator: "_").map { $0.capitalized }.joined()
        }
    }
    
    // MARK: - Pipeline Event Processing (CoT Visibility)
    
    /// Process pipeline events from the backend that expose the agent's reasoning chain
    private func processPipelineEvent(_ content: [String: Any]?) {
        guard let content = content else { return }
        guard let step = content["step"] as? String else { return }
        
        switch step.lowercased() {
        case "router":
            // Lane routing decision
            if let laneStr = content["lane"] as? String {
                let lane: AgentLane
                switch laneStr.uppercased() {
                case "FAST": lane = .fast
                case "FUNCTIONAL", "FUNC": lane = .functional
                case "WORKER": lane = .worker
                default: lane = .slow
                }
                let intent = content["intent"] as? String
                routerDecision(lane: lane, intent: intent)
                
                // Log signals if present
                if let signals = content["signals"] as? [String], !signals.isEmpty {
                    let signalsStr = signals.prefix(3).joined(separator: ", ")
                    print("[\(ts())]   │  signals: \(signalsStr)\(signals.count > 3 ? "..." : "")")
                }
            }
            
        case "planner":
            // Tool planner output with full reasoning
            var planDetails: [String] = []
            
            if let intent = content["intent"] as? String {
                planDetails.append("Intent: \(intent)")
            }
            
            if let dataNeeded = content["data_needed"] as? [String], !dataNeeded.isEmpty {
                let dataStr = dataNeeded.prefix(3).joined(separator: ", ")
                planDetails.append("Data: \(dataStr)\(dataNeeded.count > 3 ? "..." : "")")
            }
            
            if let tools = content["suggested_tools"] as? [String], !tools.isEmpty {
                let toolsStr = tools.map { humanToolName($0) }.joined(separator: " → ")
                planDetails.append("Tools: \(toolsStr)")
            }
            
            if let rationale = content["rationale"] as? String, !rationale.isEmpty {
                let shortRationale = String(rationale.prefix(60))
                planDetails.append("Why: \(shortRationale)\(rationale.count > 60 ? "..." : "")")
            }
            
            // Log planner step with full details
            if !planDetails.isEmpty {
                print("[\(ts())]   ├─ 📋 PLANNER:")
                for detail in planDetails {
                    print("[\(ts())]   │    \(detail)")
                }
            }
            
        case "thinking":
            // LLM internal reasoning (if Gemini thinking is enabled)
            if let text = content["text"] as? String, !text.isEmpty {
                thinking(text)
            }
            
        case "critic":
            // Response validation result
            if let passed = content["passed"] as? Bool {
                var criticDetail = passed ? "PASS" : "FAIL"
                
                if let findings = content["findings"] as? [String], !findings.isEmpty {
                    criticDetail += " (\(findings.count) warning\(findings.count == 1 ? "" : "s"))"
                }
                
                if let errors = content["errors"] as? [String], !errors.isEmpty {
                    criticDetail += " - \(errors.first ?? "error")"
                }
                
                pipelineStep(.critic, criticDetail)
            }
            
        case "safety", "safety_gate":
            // Safety gate check
            if let dryRun = content["dry_run"] as? Bool {
                let detail = dryRun ? "dry_run=true (awaiting confirmation)" : "executing"
                pipelineStep(.safetyGate, detail)
            }
            
        default:
            // Unknown pipeline step - log it for visibility
            print("[\(ts())]   ├─ 🔹 PIPELINE.\(step): \(content.keys.filter { $0 != "step" }.joined(separator: ", "))")
        }
    }
    
    // MARK: - SSE Event Processing
    
    /// Process raw SSE event and log appropriately
    func processSSEEvent(type: String, content: [String: Any]?, agent: String?, metadata: [String: Any]?) {
        guard enabled else { return }
        
        // Suppress noise events
        let suppressedEvents = Set(["heartbeat", "ping", "keep_alive", "keepalive"])
        if suppressedEvents.contains(type.lowercased()) { return }
        
        // Infer lane from agent if we haven't set one yet
        if currentRequest?.lane == nil {
            inferLaneFromAgent(agent)
        }
        
        switch type.lowercased() {
        case "status":
            // Status events often indicate routing
            if let text = content?["text"] as? String ?? (content?["content"] as? [String: Any])?["text"] as? String {
                if text.lowercased().contains("connect") {
                    // Skip "Connecting..." status
                } else {
                    pipelineStep(.executor, text)
                }
            }
            
        case "thinking":
            // Agent is reasoning
            if let text = content?["text"] as? String {
                thinking(text)
            }
            
        case "thought":
            // Thought completion - skip if empty
            if let text = content?["text"] as? String, !text.isEmpty {
                thinking(text)
            }
            
        case "toolrunning", "tool_running", "tool_started":
            // Tool execution started
            if let toolName = content?["tool"] as? String ?? content?["tool_name"] as? String {
                var args: [String: Any]? = nil
                if let argsDict = content?["args"] as? [String: Any] {
                    args = argsDict
                }
                toolStart(toolName, args: args)
            }
            
        case "toolcomplete", "tool_complete", "tool_result":
            // Tool execution completed
            if let toolName = content?["tool"] as? String ?? content?["tool_name"] as? String ?? content?["name"] as? String {
                var resultSummary: String? = nil
                if let result = content?["result"] as? [String: Any] {
                    if let count = result["count"] as? Int {
                        resultSummary = "\(count) items"
                    } else if let data = result["data"] as? [Any] {
                        resultSummary = "\(data.count) items"
                    } else if let success = result["success"] as? Bool {
                        resultSummary = success ? "success" : "failed"
                    }
                }
                if let counts = content?["counts"] as? [String: Any], let items = counts["items"] as? Int {
                    resultSummary = "\(items) items"
                }
                toolComplete(toolName, result: resultSummary)
            }
            
        case "message", "text_delta":
            // Text streaming - only log significant chunks
            break // Skip deltas, wait for commit
            
        case "agentresponse", "agent_response", "text_commit":
            // Committed response text
            if let text = content?["text"] as? String, !text.isEmpty {
                let isCommit = content?["is_commit"] as? Bool ?? true
                responseChunk(text, isCommit: isCommit)
            }
            
        case "routing", "route", "lane_routing":
            // Explicit routing decision
            if let laneStr = content?["lane"] as? String {
                let lane: AgentLane
                switch laneStr.lowercased() {
                case "fast": lane = .fast
                case "functional", "func": lane = .functional
                case "worker": lane = .worker
                default: lane = .slow
                }
                let intent = content?["intent"] as? String
                routerDecision(lane: lane, intent: intent)
            }
            
        case "safety_gate", "safetygate":
            // Safety gate check
            if let dryRun = content?["dry_run"] as? Bool {
                let detail = dryRun ? "dry_run=true (preview)" : "dry_run=false (executing)"
                pipelineStep(.safetyGate, detail)
            }
            
        case "critic":
            // Critic validation
            if let passed = content?["passed"] as? Bool {
                let detail = passed ? "PASS" : "FAIL"
                pipelineStep(.critic, detail)
            }
            
        case "planner":
            // Tool planner output
            if let plan = content?["plan"] as? String {
                pipelineStep(.planner, plan)
            } else if let tools = content?["tools"] as? [String] {
                pipelineStep(.planner, "Use: \(tools.joined(separator: ", "))")
            }
            
        case "error":
            // Error occurred
            if let message = content?["message"] as? String ?? content?["error"] as? String {
                pipelineStep(.error, message)
            }
            
        case "done":
            // Stream complete
            break // Handled by requestComplete
            
        case "pipeline":
            // CoT visibility events from backend (router, planner, critic, thinking)
            processPipelineEvent(content)
            
        default:
            // Log unknown event types in debug
            #if DEBUG
            print("[\(ts())]   ├─ 📌 \(type): \(content?.keys.joined(separator: ", ") ?? "empty")")
            #endif
        }
    }
}

// MARK: - Quick Access Extension

extension AgentPipelineLogger {
    /// Convenience for logging from DirectStreamingService
    static func startRequest(correlationId: String, canvasId: String?, sessionId: String?, message: String) {
        shared.requestStart(correlationId: correlationId, canvasId: canvasId, sessionId: sessionId, message: message)
    }
    
    static func endRequest(totalMs: Int? = nil, toolCount: Int? = nil) {
        shared.requestComplete(totalMs: totalMs, toolCount: toolCount)
    }
    
    static func failRequest(error: String, afterMs: Int? = nil) {
        shared.requestFailed(error: error, afterMs: afterMs)
    }
    
    static func event(type: String, content: [String: Any]?, agent: String? = nil, metadata: [String: Any]? = nil) {
        shared.processSSEEvent(type: type, content: content, agent: agent, metadata: metadata)
    }
}
