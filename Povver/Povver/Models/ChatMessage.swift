import Foundation
import UIKit

// MARK: - Chat Models
struct ChatMessage: Identifiable, Codable {
    let id: String
    let content: MessageContent
    let author: MessageAuthor
    let timestamp: Date
    var status: MessageStatus
    let metadata: MessageMetadata?
    
    init(id: String = UUID().uuidString,
         content: MessageContent,
         author: MessageAuthor,
         timestamp: Date = Date(),
         status: MessageStatus = .sent,
         metadata: MessageMetadata? = nil) {
        self.id = id
        self.content = content
        self.author = author
        self.timestamp = timestamp
        self.status = status
        self.metadata = metadata
    }
}

enum MessageContent {
    case text(String)
    case image(Data, caption: String?)
    case functionCall(name: String, status: FunctionStatus)
    case activity(String)
    case error(String)
    
    // For displaying in UI
    var displayText: String {
        switch self {
        case .text(let string):
            return string
        case .image(_, let caption):
            return caption ?? "[Image]"
        case .functionCall(let name, _):
            // Display raw function name from API
            return "Calling \(name)..."
        case .activity(let text):
            return "<" + text + ">"
        case .error(let string):
            return "Error: \(string)"
        }
    }
}

enum MessageAuthor: String, Codable {
    case user
    case agent
    case system
}

enum MessageStatus: String, Codable {
    case sending
    case sent
    case delivered
    case failed
    case streaming
}

enum FunctionStatus {
    case pending
    case executing
    case completed
    case failed
}

struct MessageMetadata: Codable {
    let functionCalls: [String]?
    let processingTime: TimeInterval?
    let tokens: Int?
}

// MARK: - Session Model
struct ChatSession: Codable, Identifiable {
    let id: String
    let userId: String
    var title: String
    var lastMessage: String?
    var lastUpdated: Date
    var messageCount: Int
    var isActive: Bool
    
    init(id: String,
         userId: String,
         title: String = "New Chat",
         lastMessage: String? = nil,
         lastUpdated: Date = Date(),
         messageCount: Int = 0,
         isActive: Bool = true) {
        self.id = id
        self.userId = userId
        self.title = title
        self.lastMessage = lastMessage
        self.lastUpdated = lastUpdated
        self.messageCount = messageCount
        self.isActive = isActive
    }
}

// MARK: - Codable Implementations
extension MessageContent: Codable {
    enum CodingKeys: String, CodingKey {
        case type, text, imageData, caption, functionName, functionStatus, error
    }
    
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        let type = try container.decode(String.self, forKey: .type)
        
        switch type {
        case "text":
            let text = try container.decode(String.self, forKey: .text)
            self = .text(text)
        case "image":
            let imageData = try container.decode(Data.self, forKey: .imageData)
            let caption = try container.decodeIfPresent(String.self, forKey: .caption)
            self = .image(imageData, caption: caption)
        case "functionCall":
            let name = try container.decode(String.self, forKey: .functionName)
            let statusRaw = try container.decode(String.self, forKey: .functionStatus)
            let status = FunctionStatus(rawValue: statusRaw) ?? .pending
            self = .functionCall(name: name, status: status)
        case "activity":
            let text = try container.decode(String.self, forKey: .text)
            self = .activity(text)
        case "error":
            let error = try container.decode(String.self, forKey: .error)
            self = .error(error)
        default:
            throw DecodingError.dataCorruptedError(forKey: .type, in: container, debugDescription: "Unknown message type")
        }
    }
    
    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        
        switch self {
        case .text(let text):
            try container.encode("text", forKey: .type)
            try container.encode(text, forKey: .text)
        case .image(let data, let caption):
            try container.encode("image", forKey: .type)
            try container.encode(data, forKey: .imageData)
            try container.encodeIfPresent(caption, forKey: .caption)
        case .functionCall(let name, let status):
            try container.encode("functionCall", forKey: .type)
            try container.encode(name, forKey: .functionName)
            try container.encode(status.rawValue, forKey: .functionStatus)
        case .activity(let text):
            try container.encode("activity", forKey: .type)
            try container.encode(text, forKey: .text)
        case .error(let error):
            try container.encode("error", forKey: .type)
            try container.encode(error, forKey: .error)
        }
    }
}

extension FunctionStatus: RawRepresentable {
    typealias RawValue = String
    
    init?(rawValue: String) {
        switch rawValue {
        case "pending": self = .pending
        case "executing": self = .executing
        case "completed": self = .completed
        case "failed": self = .failed
        default: return nil
        }
    }
    
    var rawValue: String {
        switch self {
        case .pending: return "pending"
        case .executing: return "executing"
        case .completed: return "completed"
        case .failed: return "failed"
        }
    }
} 