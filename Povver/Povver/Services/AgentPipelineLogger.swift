import Foundation

// =============================================================================
// MARK: - AgentPipelineLogger.swift — Thin facade over AppLogger
// =============================================================================
//
// Keeps AgentLane/PipelineStep enums and SSE event parsing logic.
// All output delegates to AppLogger.shared.
//
// =============================================================================

// MARK: - Lane Types (Shell Agent 4-Lane System)

enum AgentLane: String {
    case fast = "FAST"
    case slow = "SLOW"
    case functional = "FUNC"
    case worker = "WORKER"
}

// MARK: - Pipeline Steps

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
}

// MARK: - AgentPipelineLogger

final class AgentPipelineLogger {
    static let shared = AgentPipelineLogger()

    private var currentLane: AgentLane?
    private var toolCount: Int = 0
    private var startTime: Date?
    private var currentToolStart: Date?

    private init() {}

    // MARK: - Request Lifecycle

    func requestStart(correlationId: String, canvasId: String?, sessionId: String?, message: String) {
        startTime = Date()
        currentLane = nil
        toolCount = 0
        AppLogger.shared.streamStart(corr: correlationId, session: sessionId, message: message)
    }

    func routerDecision(lane: AgentLane, intent: String?) {
        currentLane = lane
        let intentStr = intent.map { " intent=\($0)" } ?? ""
        AppLogger.shared.pipeline("router", "\(lane.rawValue)_LANE\(intentStr)")
    }

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
            lane = .slow
        }
        if currentLane == nil {
            routerDecision(lane: lane, intent: nil)
        }
    }

    func pipelineStep(_ step: PipelineStep, _ detail: String, durationMs: Int? = nil) {
        let durStr = durationMs.map { " \($0)ms" } ?? ""
        AppLogger.shared.pipeline(step.rawValue.lowercased(), "\(detail)\(durStr)")
    }

    // MARK: - Tool Tracking

    func toolStart(_ name: String, args: [String: Any]? = nil) {
        currentToolStart = Date()
        AppLogger.shared.toolStart(name, args: args)
    }

    func toolComplete(_ name: String, result: String?, durationMs: Int? = nil) {
        toolCount += 1
        let ms = durationMs ?? currentToolStart.map { Int(Date().timeIntervalSince($0) * 1000) } ?? 0
        AppLogger.shared.toolDone(name, ms: ms, result: result)
        currentToolStart = nil
    }

    func toolFailed(_ name: String, error: String, durationMs: Int? = nil) {
        let ms = durationMs ?? currentToolStart.map { Int(Date().timeIntervalSince($0) * 1000) } ?? 0
        AppLogger.shared.toolFail(name, ms: ms, error: error)
        currentToolStart = nil
    }

    // MARK: - Thinking & Response

    func thinking(_ text: String? = nil) {
        guard let text, !text.isEmpty else { return }
        AppLogger.shared.pipeline("thinking", String(text.prefix(80)))
    }

    func responseChunk(_ text: String, isCommit: Bool = false) {
        guard isCommit else { return }
        AppLogger.shared.agentText(text)
    }

    // MARK: - Request Complete / Failed

    func requestComplete(totalMs: Int? = nil, toolCount: Int? = nil) {
        let ms = totalMs ?? startTime.map { Int(Date().timeIntervalSince($0) * 1000) } ?? 0
        let tools = toolCount ?? self.toolCount
        AppLogger.shared.streamEnd(ms: ms, lane: currentLane?.rawValue, tools: tools)
        reset()
    }

    func requestFailed(error: String, afterMs: Int? = nil) {
        let ms = afterMs ?? startTime.map { Int(Date().timeIntervalSince($0) * 1000) } ?? 0
        AppLogger.shared.streamAbort(error, ms: ms)
        reset()
    }

    private func reset() {
        currentLane = nil
        toolCount = 0
        startTime = nil
        currentToolStart = nil
    }

    // MARK: - SSE Event Processing

    func processSSEEvent(type: String, content: [String: Any]?, agent: String?, metadata: [String: Any]?) {
        let suppressedEvents = Set(["heartbeat", "ping", "keep_alive", "keepalive"])
        if suppressedEvents.contains(type.lowercased()) { return }

        if currentLane == nil {
            inferLaneFromAgent(agent)
        }

        switch type.lowercased() {
        case "status":
            if let text = content?["text"] as? String ?? (content?["content"] as? [String: Any])?["text"] as? String {
                if !text.lowercased().contains("connect") {
                    pipelineStep(.executor, text)
                }
            }

        case "thinking":
            if let text = content?["text"] as? String {
                thinking(text)
            }

        case "thought":
            if let text = content?["text"] as? String, !text.isEmpty {
                thinking(text)
            }

        case "toolrunning", "tool_running", "tool_started":
            if let toolName = content?["tool"] as? String ?? content?["tool_name"] as? String {
                let args = content?["args"] as? [String: Any]
                toolStart(toolName, args: args)
            }

        case "toolcomplete", "tool_complete", "tool_result":
            if let toolName = content?["tool"] as? String ?? content?["tool_name"] as? String ?? content?["name"] as? String {
                var resultSummary: String?
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
            break // Skip deltas, wait for commit

        case "agentresponse", "agent_response", "text_commit":
            if let text = content?["text"] as? String, !text.isEmpty {
                let isCommit = content?["is_commit"] as? Bool ?? true
                responseChunk(text, isCommit: isCommit)
            }

        case "routing", "route", "lane_routing":
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
            if let dryRun = content?["dry_run"] as? Bool {
                let detail = dryRun ? "dry_run=true (preview)" : "dry_run=false (executing)"
                pipelineStep(.safetyGate, detail)
            }

        case "critic":
            if let passed = content?["passed"] as? Bool {
                pipelineStep(.critic, passed ? "PASS" : "FAIL")
            }

        case "planner":
            if let plan = content?["plan"] as? String {
                pipelineStep(.planner, plan)
            } else if let tools = content?["tools"] as? [String] {
                pipelineStep(.planner, "Use: \(tools.joined(separator: ", "))")
            }

        case "error":
            if let message = content?["message"] as? String ?? content?["error"] as? String {
                pipelineStep(.error, message)
            }

        case "done":
            break // Handled by requestComplete

        case "pipeline":
            processPipelineEvent(content)

        default:
            #if DEBUG
            AppLogger.shared.pipeline(type, content?.keys.joined(separator: ", ") ?? "empty")
            #endif
        }
    }

    // MARK: - Pipeline Sub-Events

    private func processPipelineEvent(_ content: [String: Any]?) {
        guard let content, let step = content["step"] as? String else { return }

        switch step.lowercased() {
        case "router":
            if let laneStr = content["lane"] as? String {
                let lane: AgentLane
                switch laneStr.uppercased() {
                case "FAST": lane = .fast
                case "FUNCTIONAL", "FUNC": lane = .functional
                case "WORKER": lane = .worker
                default: lane = .slow
                }
                routerDecision(lane: lane, intent: content["intent"] as? String)
            }

        case "planner":
            if let tools = content["suggested_tools"] as? [String], !tools.isEmpty {
                pipelineStep(.planner, "Tools: \(tools.joined(separator: " → "))")
            } else if let intent = content["intent"] as? String {
                pipelineStep(.planner, intent)
            }

        case "thinking":
            if let text = content["text"] as? String, !text.isEmpty {
                thinking(text)
            }

        case "critic":
            if let passed = content["passed"] as? Bool {
                pipelineStep(.critic, passed ? "PASS" : "FAIL")
            }

        case "safety", "safety_gate":
            if let dryRun = content["dry_run"] as? Bool {
                pipelineStep(.safetyGate, dryRun ? "dry_run=true" : "executing")
            }

        default:
            AppLogger.shared.pipeline("pipeline.\(step)", content.keys.filter { $0 != "step" }.joined(separator: ", "))
        }
    }
}

// MARK: - Static Convenience

extension AgentPipelineLogger {
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
