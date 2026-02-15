import Foundation

/// Represents a streaming event from the agent
public struct StreamEvent: Codable {
    public enum EventType: String, Codable {
        case thinking = "thinking"
        case thought = "thought"
        case toolRunning = "toolRunning"
        case toolComplete = "toolComplete"
        case message = "message"
        case agentResponse = "agent_response"
        case userPrompt = "user_prompt"
        case userResponse = "user_response"
        case clarificationRequest = "clarification.request"
        case card = "card"
        case status = "status"
        case error = "error"
        case heartbeat = "heartbeat"
        case done = "done"
        // Pipeline events for thought process visibility (router, planner, critic)
        case pipeline = "pipeline"
        // Artifact events carry proposed cards from agent tools
        case artifact = "artifact"
    }
    
    public let type: String  // Keep as string for flexibility
    public let agent: String?
    public let content: [String: AnyCodable]?
    public let timestamp: Double?
    public let metadata: [String: AnyCodable]?
    
    // Helper to get typed event type
    public var eventType: EventType? {
        return EventType(rawValue: type)
    }
}

/// UI representation of stream events
extension StreamEvent {
    public var displayText: String {
        // Extract appropriate text based on event type
        if let message = content?["message"]?.value as? String {
            return message
        }
        if let text = content?["text"]?.value as? String {
            return text
        }
        if let status = content?["status"]?.value as? String {
            return status
        }
        if let tool = content?["tool"]?.value as? String {
            return "Running \(tool)..."
        }
        return type.capitalized
    }
    
    public var iconName: String {
        switch eventType {
        case .userPrompt:
            return "person"
        case .thinking:
            return "brain"
        case .toolRunning:
            return "gearshape"
        case .toolComplete:
            return "checkmark.circle"
        case .agentResponse:
            return "text.bubble"
        case .message:
            return "message"
        case .status:
            return "info.circle"
        case .error:
            return "exclamationmark.triangle"
        default:
            return "circle"
        }
    }
    
    public var shouldAnimate: Bool {
        return eventType == .thinking || eventType == .toolRunning
    }
    
    // Optional human readable duration for events carrying duration metadata
    public var durationText: String? {
        if let seconds = (content?["duration_s"]?.value as? Double) ??
                         (content?["duration_s"]?.value as? Int).map({ Double($0) }) ??
                         (content?["duration"]?.value as? Double) {
            return String(format: "%.1fs", seconds)
        }
        // Support milliseconds if present
        if let ms = (content?["duration_ms"]?.value as? Double) ??
                    (content?["duration_ms"]?.value as? Int).map({ Double($0) }) {
            return String(format: "%.1fs", ms / 1000.0)
        }
        return nil
    }
    
    // Whether this event indicates in-progress activity
    public var isInProgress: Bool {
        guard let t = eventType else { return false }
        switch t {
        case .thinking, .toolRunning:
            return true
        default:
            return false
        }
    }
    
    // Whether this event represents a completed action/step
    public var isCompleted: Bool {
        guard let t = eventType else { return false }
        switch t {
        case .toolComplete, .agentResponse, .thought, .done:
            return true
        default:
            return false
        }
    }
}
