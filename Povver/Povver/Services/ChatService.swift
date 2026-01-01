import Foundation
import Combine

class ChatService: ObservableObject {
    static let shared = ChatService()
    
    @Published var isLoading = false
    @Published var error: Error?
    
    // Use direct streaming service for real-time responses
    private let streamingService = DirectStreamingService()
    private let cloudFunctions = CloudFunctionService() // Keep as fallback
    private var cancellables = Set<AnyCancellable>()
    
    private init() {}
    
    // MARK: - User ID Management
    private var currentUserId: String {
        AuthService.shared.currentUser?.uid ?? ""
    }
    
    // MARK: - Session Management
    func createNewSession() async throws -> ChatSession {
        guard !currentUserId.isEmpty else {
            throw StrengthOSError.notAuthenticated
        }
        
        // Don't create a session explicitly - ADK will create one when we send the first message
        // Use a temporary ID that will be replaced by ADK's session ID
        let temporaryId = "temp-\(UUID().uuidString)"
        
        return ChatSession(
            id: temporaryId,
            userId: currentUserId,
            title: "New Chat",
            lastMessage: nil,
            lastUpdated: Date(),
            messageCount: 0,
            isActive: true
        )
    }
    
    func loadSessions() async throws -> [ChatSession] {
        // Ensure we have a current user
        guard let user = AuthService.shared.currentUser else {
            print("❌ ChatService: No authenticated user")
            throw StrengthOSError.notAuthenticated
        }
        
        print("✅ ChatService: Loading sessions for user: \(user.uid)")
        
        let sessionIds = try await streamingService.listSessions(userId: user.uid)
        
        // Fetch details for each session
        var sessions: [ChatSession] = []
        
        for (index, sessionId) in sessionIds.enumerated() {
            do {
                // Get session details
                let sessionDetails = try await streamingService.getSession(sessionId: sessionId, userId: user.uid)
                
                // Extract last message and count messages
                var lastMessageText: String?
                var messageCount = 0
                var lastTimestamp = Date(timeIntervalSince1970: sessionDetails.lastUpdateTime)
                
                // Count actual messages (excluding function calls)
                for event in sessionDetails.events {
                    if let content = event["content"] as? [String: Any],
                       let parts = content["parts"] as? [[String: Any]],
                       let role = content["role"] as? String {
                        
                        for part in parts {
                            if let text = part["text"] as? String, !text.isEmpty {
                                messageCount += 1
                                // Keep track of the last user or agent message for preview
                                if role == "user" || role == "model" {
                                    lastMessageText = text
                                    if let timestamp = event["timestamp"] as? Double {
                                        lastTimestamp = Date(timeIntervalSince1970: timestamp)
                                    }
                                }
                            }
                        }
                    }
                }
                
                // Create session with real data
                let session = ChatSession(
                    id: sessionId,
                    userId: user.uid,
                    title: "Chat Session \(index + 1)",
                    lastMessage: lastMessageText?.prefix(100).trimmingCharacters(in: .whitespacesAndNewlines),
                    lastUpdated: lastTimestamp,
                    messageCount: messageCount,
                    isActive: true
                )
                sessions.append(session)
                
            } catch {
                // If we can't load details for a session, create a basic one
                print("Failed to load details for session \(sessionId): \(error)")
                let session = ChatSession(
                    id: sessionId,
                    userId: user.uid,
                    title: "Chat Session \(index + 1)",
                    lastMessage: nil,
                    lastUpdated: Date(),
                    messageCount: 0,
                    isActive: true
                )
                sessions.append(session)
            }
        }
        
        // Sort by last updated, most recent first
        sessions.sort { $0.lastUpdated > $1.lastUpdated }
        
        return sessions
    }
    
    func deleteSession(_ sessionId: String) async throws {
        guard !currentUserId.isEmpty else {
            throw StrengthOSError.notAuthenticated
        }
        
        try await streamingService.deleteSession(sessionId: sessionId, userId: currentUserId)
    }
    
    // MARK: - Message Streaming
    func streamMessage(
        _ message: String,
        sessionId: String,
        imageData: Data? = nil
    ) -> AsyncThrowingStream<(ChatMessage, String?), Error> {
        return AsyncThrowingStream { continuation in
            Task {
                do {
                    // Handle session creation for new sessions
                    var actualSessionId = sessionId
                    if sessionId.hasPrefix("temp-") {
                        // Create a new session
                        actualSessionId = try await self.streamingService.createSession(userId: self.currentUserId)
                    }
                    
                    // Use direct streaming service
                    var previousText = ""
                    var textBuffer = ""
                    var lastFlush = Date()
                    let flushInterval: TimeInterval = 2.0 // Increased to allow more accumulation
                    var isFirstTextMessage = true
                    var hasShownThinking = false
                    var hasEmittedText = false
                    
                    // Show initial thinking indicator
                    let thinkingMessage = ChatMessage(
                        content: .activity("Thinking"),
                        author: .agent,
                        timestamp: Date(),
                        status: .sent
                    )
                    continuation.yield((thinkingMessage, actualSessionId))
                    hasShownThinking = true
                    
                    self.streamingService.streamQuery(
                        message: message,
                        userId: self.currentUserId,
                        sessionId: actualSessionId,
                        progressHandler: { partialText, action in
                            if let action = action {
                                // Remove thinking indicator if shown
                                if hasShownThinking {
                                    let removeThinking = ChatMessage(
                                        content: .activity("REMOVE_THINKING"),
                                        author: .agent,
                                        timestamp: Date(),
                                        status: .sent
                                    )
                                    continuation.yield((removeThinking, actualSessionId))
                                    hasShownThinking = false
                                }
                                
                                let activityMessage = ChatMessage(
                                    content: .activity(action),
                                    author: .agent,
                                    timestamp: Date(),
                                    status: .sent
                                )
                                continuation.yield((activityMessage, actualSessionId))
                                
                                // Show thinking again after tool call
                                Thread.sleep(forTimeInterval: 0.5)
                                let thinkingAgain = ChatMessage(
                                    content: .activity("Thinking"),
                                    author: .agent,
                                    timestamp: Date(),
                                    status: .sent
                                )
                                continuation.yield((thinkingAgain, actualSessionId))
                                hasShownThinking = true
                                return
                            }
                            guard let partialText = partialText else { return }
                            
                            // Remove thinking indicator when we start receiving text
                            if hasShownThinking && !partialText.isEmpty {
                                let removeThinking = ChatMessage(
                                    content: .activity("REMOVE_THINKING"),
                                    author: .agent,
                                    timestamp: Date(),
                                    status: .sent
                                )
                                continuation.yield((removeThinking, actualSessionId))
                                hasShownThinking = false
                            }
                            
                            // Remove typing indicator; rely on streamed chunks only
                            if isFirstTextMessage && !partialText.isEmpty {
                                isFirstTextMessage = false
                            }
                            
                            // Aggregate into buffer
                            let delta = String(partialText.dropFirst(previousText.count))
                            guard !delta.isEmpty else { return }
                            previousText = partialText
                            textBuffer += delta
                            let now = Date()

                            func shouldFlushBuffer() -> Bool {
                                // Check if we should flush based on content
                                let trimmed = textBuffer.trimmingCharacters(in: .whitespacesAndNewlines)
                                
                                // Don't flush if buffer is too small (unless timeout)
                                if trimmed.count < 60 && now.timeIntervalSince(lastFlush) < flushInterval {
                                    return false
                                }
                                
                                // Check for natural breaking points
                                if textBuffer.contains("\n\n") {
                                    // But check if we're in the middle of a list
                                    let lines = textBuffer.components(separatedBy: "\n")
                                    let lastLine = lines.last?.trimmingCharacters(in: .whitespaces) ?? ""
                                    let secondLastLine = lines.dropLast().last?.trimmingCharacters(in: .whitespaces) ?? ""
                                    
                                    // Don't break if we're in a numbered list
                                    if lastLine.matches("^\\d+\\.\\s") || secondLastLine.matches("^\\d+\\.\\s") {
                                        return false
                                    }
                                    
                                    // Don't break if the last line is a header (ends with :)
                                    if lastLine.hasSuffix(":") && lastLine.count < 50 {
                                        return false
                                    }
                                    
                                    return true
                                }
                                
                                // Flush on timeout
                                return now.timeIntervalSince(lastFlush) > flushInterval
                            }
                            
                            func flushBuffer() {
                                let trimmed = textBuffer.trimmingCharacters(in: .whitespacesAndNewlines)
                                guard !trimmed.isEmpty else { return }
                                
                                let msg = ChatMessage(
                                    content: .text(trimmed),
                                    author: .agent,
                                    timestamp: Date(),
                                    status: .streaming
                                )
                                continuation.yield((msg, actualSessionId))
                                hasEmittedText = true
                                
                                textBuffer = ""
                                lastFlush = now
                                
                                // Add slight delay between messages for natural feel
                                Thread.sleep(forTimeInterval: 0.3)
                            }

                            if shouldFlushBuffer() {
                                flushBuffer()
                            }
                        },
                        completion: { result in
                            switch result {
                            case .success(let (finalResponse, returnedSessionId)):
                                // Remove any remaining thinking indicator
                                if hasShownThinking {
                                    let removeThinking = ChatMessage(
                                        content: .activity("REMOVE_THINKING"),
                                        author: .agent,
                                        timestamp: Date(),
                                        status: .sent
                                    )
                                    continuation.yield((removeThinking, actualSessionId))
                                }
                                
                                // Check if we have unsent content in the final response
                                let trimmedBuffer = textBuffer.trimmingCharacters(in: .whitespacesAndNewlines)
                                let trimmedFinal = finalResponse.trimmingCharacters(in: .whitespacesAndNewlines)
                                
                                // If finalResponse has more content than what we've sent so far
                                if !trimmedFinal.isEmpty && trimmedFinal != previousText {
                                    // Extract any remaining content
                                    let remainingContent = String(trimmedFinal.dropFirst(previousText.count))
                                    let contentToSend = trimmedBuffer.isEmpty ? remainingContent : (trimmedBuffer + remainingContent)
                                    
                                    if !contentToSend.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                                        let finalMsg = ChatMessage(
                                            content: .text(contentToSend.trimmingCharacters(in: .whitespacesAndNewlines)),
                                            author: .agent,
                                            timestamp: Date(),
                                            status: .sent
                                        )
                                        continuation.yield((finalMsg, returnedSessionId ?? actualSessionId))
                                        hasEmittedText = true
                                    }
                                } else if !trimmedBuffer.isEmpty {
                                    // Just flush the buffer if no new content in finalResponse
                                    let finalMsg = ChatMessage(
                                        content: .text(trimmedBuffer),
                                        author: .agent,
                                        timestamp: Date(),
                                        status: .sent
                                    )
                                    continuation.yield((finalMsg, returnedSessionId ?? actualSessionId))
                                    hasEmittedText = true
                                } else if !hasEmittedText && !trimmedFinal.isEmpty {
                                    // Edge case: small single-commit responses never flushed during stream
                                    let finalMsg = ChatMessage(
                                        content: .text(trimmedFinal),
                                        author: .agent,
                                        timestamp: Date(),
                                        status: .sent
                                    )
                                    continuation.yield((finalMsg, returnedSessionId ?? actualSessionId))
                                    hasEmittedText = true
                                }
                                
                                continuation.finish()
                                
                            case .failure(let error):
                                // Show error message
                                print("Streaming error: \(error.localizedDescription)")
                                let errorMessage = ChatMessage(
                                    content: .error(error.localizedDescription),
                                    author: .system,
                                    timestamp: Date()
                                )
                                continuation.yield((errorMessage, nil))
                                continuation.finish(throwing: error)
                            }
                        }
                    )
                } catch {
                    // Show error message
                    let errorMessage = ChatMessage(
                        content: .error(error.localizedDescription),
                        author: .system,
                        timestamp: Date()
                    )
                    continuation.yield((errorMessage, nil))
                    continuation.finish(throwing: error)
                }
            }
        }
    }
    
    // MARK: - Message Conversion
    func convertToUIMessages(from streamEvents: AsyncThrowingStream<ChatMessage, Error>) async throws -> [ChatMessage] {
        var messages: [ChatMessage] = []
        
        for try await message in streamEvents {
            messages.append(message)
        }
        
        return messages
    }
    
    // MARK: - Session Message Loading
    func loadSessionMessages(for sessionId: String) async throws -> [ChatMessage] {
        guard !currentUserId.isEmpty else {
            throw StrengthOSError.notAuthenticated
        }
        
        // Don't try to load messages for temporary sessions
        if sessionId.hasPrefix("temp-") {
            return []
        }
        
        // Fetch session details from ADK
        let sessionDetails = try await streamingService.getSession(sessionId: sessionId, userId: currentUserId)
        
        // Parse events into ChatMessages
        var messages: [ChatMessage] = []
        
        for event in sessionDetails.events {
            // Skip events without content
            guard let content = event["content"] as? [String: Any],
                  let parts = content["parts"] as? [[String: Any]],
                  let role = content["role"] as? String else {
                continue
            }
            
            // Determine author
            let author: MessageAuthor = (role == "user") ? .user : .agent
            
            // Parse timestamp
            let timestamp = Date(timeIntervalSince1970: event["timestamp"] as? Double ?? 0)
            
            // Process each part
            for part in parts {
                if let text = part["text"] as? String, !text.isEmpty {
                    // Text message
                    let message = ChatMessage(
                        content: .text(text),
                        author: author,
                        timestamp: timestamp,
                        status: .sent
                    )
                    messages.append(message)
                } else if let functionCall = part["function_call"] as? [String: Any],
                          let name = functionCall["name"] as? String {
                    // Function call - convert to activity message
                    let args = functionCall["args"] as? [String: Any]
                    let humanReadableName = getHumanReadableFunctionName(name)
                    let argsString = formatFunctionArgs(args)
                    
                    let message = ChatMessage(
                        content: .activity("\(humanReadableName)\(argsString)"),
                        author: .agent,
                        timestamp: timestamp,
                        status: .sent
                    )
                    messages.append(message)
                }
            }
        }
        
        return messages
    }
    
    // Helper methods for formatting (borrowed from DirectStreamingService logic)
    private func getHumanReadableFunctionName(_ name: String) -> String {
        switch name {
        // New unified agent tools
        case "tool_set_context": return "Setting up"
        case "tool_search_exercises": return "Searching exercises"
        case "tool_get_user_profile", "tool_fetch_profile": return "Reviewing profile"
        case "tool_get_recent_workouts", "tool_fetch_recent_sessions": return "Checking history"
        case "tool_ask_user", "tool_request_clarification": return "Asking question"
        case "tool_create_workout_plan": return "Creating plan"
        case "tool_publish_workout_plan", "tool_publish_cards": return "Publishing plan"
        case "tool_record_user_info": return "Recording info"
        case "tool_emit_status", "tool_emit_agent_event": return "Logging"
        case "tool_send_message": return "Sending message"
        // Legacy tools
        case "get_user": return "Loading user profile"
        case "get_user_workouts": return "Loading workout history"
        case "get_workout": return "Getting workout details"
        case "get_user_templates": return "Fetching templates"
        case "get_template": return "Getting template details"
        case "create_template": return "Creating template"
        case "update_template": return "Updating template"
        case "delete_template": return "Deleting template"
        case "get_user_routines": return "Fetching routines"
        case "get_active_routine": return "Checking active routine"
        case "get_routine": return "Getting routine details"
        case "create_routine": return "Creating routine"
        case "update_routine": return "Updating routine"
        case "delete_routine": return "Deleting routine"
        case "set_active_routine": return "Activating routine"
        case "list_exercises": return "Browsing exercises"
        case "search_exercises": return "Searching exercises"
        case "get_exercise": return "Getting exercise details"
        case "update_user": return "Updating user profile"
        case "get_my_user_id": return "Checking user session"
        case "store_important_fact": return "Remembering important information"
        case "get_important_facts": return "Recalling stored information"
        default: return name.replacingOccurrences(of: "tool_", with: "").replacingOccurrences(of: "_", with: " ").capitalized
        }
    }
    
    private func formatFunctionArgs(_ args: [String: Any]?) -> String {
        guard let args = args, !args.isEmpty else { return "" }
        
        var displayParts: [String] = []
        
        // Extract key arguments for display (excluding user_id)
        if let startDate = args["start_date"] as? String {
            displayParts.append("from \(formatDate(startDate))")
        }
        if let endDate = args["end_date"] as? String {
            displayParts.append("to \(formatDate(endDate))")
        }
        if let limit = args["limit"] {
            displayParts.append("limit: \(limit)")
        }
        if let muscleGroups = args["muscle_groups"] as? String {
            displayParts.append("muscles: \(muscleGroups)")
        }
        if let equipment = args["equipment"] as? String {
            displayParts.append("equipment: \(equipment)")
        }
        if let query = args["query"] as? String {
            displayParts.append("'\(query)'")
        }
        if let name = args["name"] as? String {
            displayParts.append("'\(name)'")
        }
        
        if displayParts.isEmpty {
            return ""
        }
        
        return " (" + displayParts.joined(separator: ", ") + ")"
    }
    
    private func formatDate(_ isoString: String) -> String {
        let formatter = ISO8601DateFormatter()
        if let date = formatter.date(from: isoString) {
            let displayFormatter = DateFormatter()
            displayFormatter.dateStyle = .medium
            displayFormatter.timeStyle = .none
            return displayFormatter.string(from: date)
        }
        return isoString
    }
}
