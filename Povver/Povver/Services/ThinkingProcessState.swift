import Foundation
import Combine

// =============================================================================
// MARK: - ThinkingProcessState.swift - Gemini-Style Thought Process
// =============================================================================
//
// PURPOSE:
// Unified state management for the agent's thinking process, replacing the
// fragmented ThoughtTrackView, StreamOverlay, and AgentProgressState.
//
// DESIGN PRINCIPLES:
// 1. ONE STATE - Single source of truth for thinking UI
// 2. GROUPED STEPS - Multiple tools grouped into "Gathering information"
// 3. COLLAPSED BY DEFAULT - One line, expandable on tap
// 4. AUTO-COLLAPSE ON COMPLETE - Smooth transition when done
//
// USAGE:
//   @StateObject private var thinkingState = ThinkingProcessState()
//   thinkingState.handleEvent(event)  // Called from CanvasViewModel
//   ThinkingBubble(state: thinkingState)  // Used in UI
//
// =============================================================================

// MARK: - Thinking Step Model

/// A single step in the thinking process
public struct ThinkingStep: Identifiable, Equatable {
    public let id: String
    public let phase: ThinkingPhase
    public let title: String
    public var detail: String?
    public var status: StepStatus
    public let timestamp: Date
    public var durationMs: Int?
    
    public enum StepStatus: Equatable {
        case pending
        case active
        case complete
        case error(String)
    }
    
    public init(
        id: String = UUID().uuidString,
        phase: ThinkingPhase,
        title: String,
        detail: String? = nil,
        status: StepStatus = .pending,
        timestamp: Date = Date(),
        durationMs: Int? = nil
    ) {
        self.id = id
        self.phase = phase
        self.title = title
        self.detail = detail
        self.status = status
        self.timestamp = timestamp
        self.durationMs = durationMs
    }
    
    /// Duration formatted as string
    public var durationText: String? {
        guard let ms = durationMs else { return nil }
        return String(format: "%.1fs", Double(ms) / 1000.0)
    }
}

// MARK: - Thinking Phase

/// The major phases of agent work - used for grouping
public enum ThinkingPhase: String, CaseIterable {
    case planning = "Planning approach"
    case gathering = "Gathering information"
    case building = "Building response"
    case finalizing = "Finalizing"
    
    /// SF Symbol for this phase
    public var icon: String {
        switch self {
        case .planning: return "brain"
        case .gathering: return "magnifyingglass"
        case .building: return "hammer"
        case .finalizing: return "checkmark.circle"
        }
    }
    
    /// Derive phase from tool name
    public static func from(toolName: String) -> ThinkingPhase {
        let name = toolName.lowercased()
        
        // Context/search tools → gathering
        if name.contains("context") || name.contains("profile") || 
           name.contains("search") || name.contains("history") ||
           name.contains("workout") || name.contains("template") ||
           name.contains("routine") && !name.contains("propose") {
            return .gathering
        }
        
        // Proposal/creation tools → building
        if name.contains("propose") || name.contains("create") || 
           name.contains("build") || name.contains("format") {
            return .building
        }
        
        // Publish/save tools → finalizing
        if name.contains("publish") || name.contains("save") ||
           name.contains("emit") {
            return .finalizing
        }
        
        return .gathering  // Default
    }
    
    /// Derive phase from pipeline step
    public static func from(pipelineStep: String) -> ThinkingPhase {
        switch pipelineStep.lowercased() {
        case "router", "planner": return .planning
        case "critic": return .finalizing
        default: return .building
        }
    }
}

// MARK: - Thinking Process State

/// Main state object for the thinking process UI
@MainActor
public final class ThinkingProcessState: ObservableObject {
    
    // MARK: - Published State
    
    /// All steps in the current thinking process
    @Published public private(set) var steps: [ThinkingStep] = []
    
    /// Current active phase for the header display
    @Published public private(set) var currentPhase: ThinkingPhase = .planning
    
    /// Whether the process is complete
    @Published public private(set) var isComplete: Bool = false
    
    /// Whether the bubble is expanded (collapsed by default)
    @Published public var isExpanded: Bool = false
    
    /// Total duration in milliseconds
    @Published public private(set) var totalDurationMs: Int = 0
    
    // MARK: - Internal State
    
    private var startTime: Date?
    private var activeToolStarts: [String: Date] = [:]
    private var toolPhaseMap: [String: ThinkingPhase] = [:]
    
    public init() {}
    
    // MARK: - Computed Properties
    
    /// The summary text shown in collapsed state
    public var summaryText: String {
        if isComplete {
            return "Show thinking"
        }
        return currentPhase.rawValue
    }
    
    /// Duration formatted for display
    public var totalDurationText: String {
        String(format: "%.1fs", Double(totalDurationMs) / 1000.0)
    }
    
    /// Whether there is active work happening
    public var isActive: Bool {
        !isComplete && !steps.isEmpty
    }
    
    /// Whether there are any active steps
    public var hasActiveSteps: Bool {
        steps.contains { $0.status == .active }
    }
    
    // MARK: - Event Handling
    
    /// Handle an incoming stream event
    public func handleEvent(_ event: StreamEvent) {
        guard let eventType = event.eventType else { return }
        
        switch eventType {
        case .pipeline:
            handlePipelineEvent(event)
            
        case .thinking:
            handleThinkingStart(event)
            
        case .thought:
            handleThoughtComplete(event)
            
        case .toolRunning:
            handleToolStart(event)
            
        case .toolComplete:
            handleToolComplete(event)
            
        case .done:
            handleDone()
            
        case .error:
            handleError(event)
            
        default:
            break
        }
    }
    
    /// Reset for a new request
    public func reset() {
        steps = []
        currentPhase = .planning
        isComplete = false
        isExpanded = false
        totalDurationMs = 0
        startTime = nil
        activeToolStarts.removeAll()
        toolPhaseMap.removeAll()
    }
    
    /// Start a new thinking process
    public func start() {
        reset()
        startTime = Date()
        
        // Add initial "Planning approach" step
        steps.append(ThinkingStep(
            phase: .planning,
            title: "Planning approach",
            status: .active
        ))
        currentPhase = .planning
    }
    
    /// Mark the thinking process as complete
    public func complete() {
        handleDone()
    }
    
    // MARK: - Private Event Handlers
    
    private func handlePipelineEvent(_ event: StreamEvent) {
        guard let step = event.content?["step"]?.value as? String else { return }
        
        let phase = ThinkingPhase.from(pipelineStep: step)
        
        switch step.lowercased() {
        case "router":
            // Router decision - update planning step with lane info
            let lane = event.content?["lane"]?.value as? String ?? "slow"
            let intent = event.content?["intent"]?.value as? String
            
            updateStep(forPhase: .planning) { step in
                step.detail = intent != nil ? "Intent: \(intent!)" : "Lane: \(lane)"
                step.status = .complete
            }
            
        case "planner":
            // Planner output - show the plan summary
            let planIntent = event.content?["intent"]?.value as? String
            let rationale = event.content?["rationale"]?.value as? String
            let tools = event.content?["suggested_tools"]?.value as? [String] ?? []
            
            // Complete the planning step
            updateStep(forPhase: .planning) { step in
                if let intent = planIntent {
                    step.detail = intent
                }
                step.status = .complete
            }
            
            // Add a gathering step if there are tools
            if !tools.isEmpty {
                currentPhase = .gathering
                steps.append(ThinkingStep(
                    phase: .gathering,
                    title: "Gathering information",
                    detail: "\(tools.count) steps planned",
                    status: .active
                ))
            }
            
        case "critic":
            // Critic validation
            let passed = event.content?["passed"]?.value as? Bool ?? true
            
            steps.append(ThinkingStep(
                phase: .finalizing,
                title: "Validating response",
                detail: passed ? "Passed" : "Issues found",
                status: .complete
            ))
            
        default:
            break
        }
    }
    
    private func handleThinkingStart(_ event: StreamEvent) {
        // If we don't have a start time, this is the beginning
        if startTime == nil {
            start()
        }
    }
    
    private func handleThoughtComplete(_ event: StreamEvent) {
        // Complete any active thinking step
        updateActiveStep { step in
            step.status = .complete
        }
    }
    
    private func handleToolStart(_ event: StreamEvent) {
        let toolName = (event.content?["tool"]?.value as? String) ??
                       (event.content?["tool_name"]?.value as? String) ?? "tool"
        let displayText = event.content?["text"]?.value as? String
        
        // Track start time for duration calculation
        activeToolStarts[toolName] = Date()
        
        // Determine phase for this tool
        let phase = ThinkingPhase.from(toolName: toolName)
        toolPhaseMap[toolName] = phase
        
        // Update current phase if needed
        if phase != currentPhase {
            // Complete the current phase step
            updateStep(forPhase: currentPhase) { step in
                step.status = .complete
            }
            
            currentPhase = phase
            
            // Check if we already have a step for this phase
            if !steps.contains(where: { $0.phase == phase && $0.status != .complete }) {
                steps.append(ThinkingStep(
                    phase: phase,
                    title: phase.rawValue,
                    status: .active
                ))
            }
        }
        
        // Update the current phase step with tool info
        updateStep(forPhase: phase) { step in
            if step.status != .active {
                step.status = .active
            }
            // Update detail with current tool
            step.detail = displayText ?? humanReadableToolName(toolName)
        }
    }
    
    private func handleToolComplete(_ event: StreamEvent) {
        let toolName = (event.content?["tool"]?.value as? String) ??
                       (event.content?["tool_name"]?.value as? String) ?? "tool"
        let displayText = event.content?["text"]?.value as? String
        
        // Calculate duration
        var durationMs: Int?
        if let startTime = activeToolStarts.removeValue(forKey: toolName) {
            durationMs = Int(Date().timeIntervalSince(startTime) * 1000)
        }
        
        // Get phase for this tool
        let phase = toolPhaseMap.removeValue(forKey: toolName) ?? currentPhase
        
        // Update the phase step
        updateStep(forPhase: phase) { step in
            step.detail = displayText ?? humanReadableToolName(toolName)
            if let ms = durationMs {
                step.durationMs = (step.durationMs ?? 0) + ms
            }
            // Don't mark complete yet - more tools might be in this phase
        }
    }
    
    private func handleDone() {
        // Complete all active steps
        for i in steps.indices {
            if steps[i].status == .active {
                steps[i].status = .complete
            }
        }
        
        // Calculate total duration
        if let start = startTime {
            totalDurationMs = Int(Date().timeIntervalSince(start) * 1000)
        }
        
        isComplete = true
        
        // Auto-collapse after a short delay
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { [weak self] in
            withAnimation(.easeInOut(duration: 0.3)) {
                self?.isExpanded = false
            }
        }
    }
    
    private func handleError(_ event: StreamEvent) {
        let errorText = event.content?["text"]?.value as? String ??
                        event.content?["error"]?.value as? String ?? "An error occurred"
        
        // Mark current step as error
        updateActiveStep { step in
            step.status = .error(errorText)
        }
        
        isComplete = true
    }
    
    // MARK: - Helpers
    
    private func updateStep(forPhase phase: ThinkingPhase, modifier: (inout ThinkingStep) -> Void) {
        if let index = steps.lastIndex(where: { $0.phase == phase }) {
            modifier(&steps[index])
        }
    }
    
    private func updateActiveStep(modifier: (inout ThinkingStep) -> Void) {
        if let index = steps.lastIndex(where: { $0.status == .active }) {
            modifier(&steps[index])
        }
    }
    
    private func humanReadableToolName(_ name: String) -> String {
        let cleaned = name
            .replacingOccurrences(of: "tool_", with: "")
            .replacingOccurrences(of: "_", with: " ")
        return cleaned.prefix(1).uppercased() + cleaned.dropFirst()
    }
}

// MARK: - Xcode Debug Logging

extension ThinkingProcessState {
    /// Log current state to Xcode console for debugging
    public func logState() {
        #if DEBUG
        print("┌─ ThinkingProcessState ──────────────────")
        print("│ Phase: \(currentPhase.rawValue)")
        print("│ Complete: \(isComplete)")
        print("│ Steps: \(steps.count)")
        for step in steps {
            let statusIcon: String
            switch step.status {
            case .pending: statusIcon = "⏳"
            case .active: statusIcon = "🔄"
            case .complete: statusIcon = "✅"
            case .error: statusIcon = "❌"
            }
            print("│   \(statusIcon) [\(step.phase.rawValue)] \(step.title)")
            if let detail = step.detail {
                print("│       └─ \(detail)")
            }
        }
        print("└──────────────────────────────────────────")
        #endif
    }
}
