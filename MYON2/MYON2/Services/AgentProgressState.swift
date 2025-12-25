import Foundation
import Combine

/// Centralized agent progress tracking with monotonic progression.
/// Progress only advances, never regresses - even if events arrive out of order.
@MainActor
public final class AgentProgressState: ObservableObject {
    
    // MARK: - Progress Stage
    
    public enum Stage: Int, Comparable, CaseIterable {
        case idle = 0
        case understanding = 1   // Fetching profile, context
        case searching = 2       // Searching exercises
        case building = 3        // Creating workout plan
        case finalizing = 4      // Publishing cards
        case complete = 5
        
        public static func < (lhs: Stage, rhs: Stage) -> Bool {
            lhs.rawValue < rhs.rawValue
        }
        
        /// User-facing display text for this stage
        public var displayText: String {
            switch self {
            case .idle: return ""
            case .understanding: return "Understanding request"
            case .searching: return "Finding exercises"
            case .building: return "Building plan"
            case .finalizing: return "Finalizing"
            case .complete: return ""
            }
        }
        
        /// Icon for this stage (SF Symbol name)
        public var icon: String? {
            switch self {
            case .idle: return nil
            case .understanding: return "person.circle"
            case .searching: return "magnifyingglass"
            case .building: return "hammer"
            case .finalizing: return "checkmark.circle"
            case .complete: return nil
            }
        }
    }
    
    // MARK: - Published State
    
    /// Current highest stage reached (monotonic)
    @Published private(set) public var currentStage: Stage = .idle
    
    /// Whether the agent is actively working
    @Published private(set) public var isActive: Bool = false
    
    /// Timestamp when current work started
    @Published private(set) public var startedAt: Date?
    
    /// Timestamp when work completed
    @Published private(set) public var completedAt: Date?
    
    // MARK: - Tool Name Mapping
    
    /// Map a raw tool name to a progress stage.
    /// Unknown tools return nil (caller should fall back to current stage or "Working")
    public static func stage(for toolName: String) -> Stage? {
        switch toolName {
        // Understanding phase
        case "tool_get_user_profile",
             "tool_fetch_profile",
             "tool_set_canvas_context",
             "tool_set_context":
            return .understanding
            
        // Searching phase
        case "tool_search_exercises",
             "list_exercises",
             "search_exercises":
            return .searching
            
        // Building phase
        case "tool_propose_workout",
             "tool_create_workout_plan",
             "tool_format_workout_plan_cards":
            return .building
            
        // Finalizing phase
        case "tool_publish_workout_plan",
             "tool_publish_cards",
             "tool_emit_agent_event":
            return .finalizing
            
        default:
            return nil  // Unknown tool - falls back gracefully
        }
    }
    
    /// User-facing label for a tool name.
    /// Falls back to "Working" for unknown tools.
    public static func displayText(for toolName: String) -> String {
        if let stage = stage(for: toolName) {
            return stage.displayText
        }
        return "Working"
    }
    
    // MARK: - State Transitions
    
    /// Advance to a stage if it's higher than current.
    /// This is monotonic - calling with a lower stage has no effect.
    public func advance(to stage: Stage) {
        guard stage > currentStage else { return }
        
        if currentStage == .idle {
            startedAt = Date()
        }
        
        currentStage = stage
        isActive = stage != .idle && stage != .complete
        
        DebugLogger.debug(.canvas, "Progress: \(stage.displayText) (stage \(stage.rawValue))")
    }
    
    /// Advance using a tool name. Unknown tools are ignored.
    public func advance(with toolName: String) {
        if let stage = Self.stage(for: toolName) {
            advance(to: stage)
        }
    }
    
    /// Mark work as complete
    public func complete() {
        currentStage = .complete
        isActive = false
        completedAt = Date()
        
        if let start = startedAt {
            let duration = Date().timeIntervalSince(start)
            DebugLogger.debug(.canvas, "Progress complete in \(String(format: "%.1f", duration))s")
        }
    }
    
    /// Reset to idle state (for new work session)
    public func reset() {
        currentStage = .idle
        isActive = false
        startedAt = nil
        completedAt = nil
    }
    
    // MARK: - Computed
    
    /// Progress fraction (0.0 - 1.0) for progress indicators
    public var progressFraction: Double {
        switch currentStage {
        case .idle: return 0.0
        case .understanding: return 0.2
        case .searching: return 0.4
        case .building: return 0.7
        case .finalizing: return 0.9
        case .complete: return 1.0
        }
    }
    
    /// Duration since work started (nil if not started)
    public var elapsedTime: TimeInterval? {
        guard let start = startedAt else { return nil }
        let end = completedAt ?? Date()
        return end.timeIntervalSince(start)
    }
}
