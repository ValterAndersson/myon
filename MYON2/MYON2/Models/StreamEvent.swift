import Foundation

/// Represents a streaming event from the agent
public struct StreamEvent: Codable {
    public enum EventType: String, Codable {
        case agentThinking = "agent_thinking"
        case agentThought = "agent_thought"
        case agentTool = "agent_tool"
        case agentMessage = "agent_message"
        case agentCard = "agent_card"
        case heartbeat = "heartbeat"
        case done = "done"
    }
    
    public enum DisplayType: String, Codable {
        case inline = "inline"      // Shows inline with timer
        case block = "block"        // Shows as message block
        case card = "card"          // Shows as card
    }
    
    public let type: EventType
    public let seq: Int
    public let ts: Int64
    public let display: DisplayType?
    public let content: StreamContent?
}

public struct StreamContent: Codable {
    // Common fields
    public let status: String?
    public let message: String?
    public let text: String?
    
    // Tool-specific
    public let tool: String?
    public let description: String?
    public let duration: String?
    
    // Card content
    public let cardType: String?
    public let cardData: [String: AnyCodable]?
    
    enum CodingKeys: String, CodingKey {
        case status, message, text, tool, description, duration
        case cardType = "type"
        case cardData = "content"
    }
}

/// UI model for displaying stream events
public struct StreamDisplay {
    public enum Style {
        case thinking(startTime: Date)
        case thought(message: String, duration: String?)
        case toolRunning(name: String, description: String, startTime: Date)
        case toolComplete(name: String, duration: String?)
        case message(text: String)
        case card(type: String, data: [String: Any])
    }
    
    public let id: String
    public let style: Style
    public let timestamp: Date
    
    public init(from event: StreamEvent) {
        self.id = "\(event.seq)"
        self.timestamp = Date(timeIntervalSince1970: Double(event.ts) / 1000.0)
        
        switch event.type {
        case .agentThinking:
            self.style = .thinking(startTime: timestamp)
            
        case .agentThought:
            let message = event.content?.message ?? ""
            let duration = event.content?.duration
            self.style = .thought(message: message, duration: duration)
            
        case .agentTool:
            let toolName = event.content?.tool ?? "tool"
            if event.content?.status == "running" {
                let description = event.content?.description ?? toolName
                self.style = .toolRunning(
                    name: toolName,
                    description: description,
                    startTime: timestamp
                )
            } else {
                let duration = event.content?.duration
                self.style = .toolComplete(name: toolName, duration: duration)
            }
            
        case .agentMessage:
            let text = event.content?.text ?? event.content?.message ?? ""
            self.style = .message(text: text)
            
        case .agentCard:
            let type = event.content?.cardType ?? "unknown"
            let data = event.content?.cardData?.mapValues { $0.value } ?? [:]
            self.style = .card(type: type, data: data)
            
        default:
            self.style = .message(text: "")
        }
    }
    
    /// Format the display for UI
    public var displayText: String {
        switch style {
        case .thinking:
            return "🤔 Thinking..."
            
        case .thought(let message, let duration):
            if let duration = duration {
                return "💭 Thought for \(duration): \(message)"
            } else {
                return "💭 \(message)"
            }
            
        case .toolRunning(_, let description, _):
            return "⚙️ \(description)..."
            
        case .toolComplete(let name, let duration):
            let readableName = name.replacingOccurrences(of: "_", with: " ")
            if let duration = duration {
                return "✅ \(readableName) (\(duration))"
            } else {
                return "✅ \(readableName)"
            }
            
        case .message(let text):
            return text
            
        case .card:
            return "" // Cards are rendered separately
        }
    }
    
    /// Whether this should show a timer
    public var showsTimer: Bool {
        switch style {
        case .thinking, .toolRunning:
            return true
        default:
            return false
        }
    }
}
