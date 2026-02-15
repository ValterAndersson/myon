import Foundation

/// ViewModel for workout coach chat during active workout.
/// Chat is ephemeral (in-memory only, not persisted to Firestore).
///
/// Streaming pattern mirrors CanvasViewModel:
/// - .message events: accumulate text deltas via displayText
/// - .done event: flush messageBuffer as final agent response
/// - .status events: extract session_id for conversation continuity
@MainActor
final class WorkoutCoachViewModel: ObservableObject {
    @Published var messages: [ChatMessage] = []
    @Published var isStreaming = false
    @Published var inputText = ""

    private(set) var workoutId: String
    let conversationId: String
    private var currentSessionId: String?

    init(workoutId: String, conversationId: String = "workout-coach") {
        self.workoutId = workoutId
        self.conversationId = conversationId
    }

    /// Update workout context. Resets conversation for a different workout.
    func updateWorkout(_ workoutId: String) {
        guard workoutId != self.workoutId else { return }
        self.workoutId = workoutId
        self.messages = []
        self.currentSessionId = nil
    }

    func send() async {
        let text = inputText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, !isStreaming else { return }

        inputText = ""

        let userMsg = ChatMessage(
            content: .text(text),
            author: .user
        )
        messages.append(userMsg)

        guard let userId = AuthService.shared.currentUser?.uid else {
            messages.append(ChatMessage(
                content: .error("Not authenticated"),
                author: .system
            ))
            return
        }

        isStreaming = true

        // Placeholder for streaming agent response
        let agentMsgId = UUID().uuidString
        messages.append(ChatMessage(
            id: agentMsgId,
            content: .text(""),
            author: .agent,
            status: .streaming
        ))

        // Accumulate text deltas (same pattern as CanvasViewModel.messageBuffer)
        var messageBuffer = ""

        do {
            let stream = DirectStreamingService.shared.streamQuery(
                userId: userId,
                conversationId: conversationId,
                message: text,
                correlationId: UUID().uuidString,
                sessionId: currentSessionId,
                workoutId: workoutId
            )

            for try await event in stream {
                switch event.eventType {
                case .message:
                    // Text delta — accumulate via displayText
                    let delta = event.displayText
                    if !delta.isEmpty {
                        messageBuffer += delta
                        updateAgentMessage(id: agentMsgId, text: messageBuffer, status: .streaming)
                    }

                case .status:
                    if let sid = event.content?["session_id"]?.value as? String {
                        currentSessionId = sid
                    }

                case .toolRunning:
                    // Show tool label briefly while waiting
                    let toolLabel = event.displayText
                    if !toolLabel.isEmpty && messageBuffer.isEmpty {
                        updateAgentMessage(id: agentMsgId, text: toolLabel, status: .streaming)
                    }

                case .toolComplete:
                    break

                case .done:
                    // Flush: use accumulated buffer as final response
                    let response = messageBuffer.trimmingCharacters(in: .whitespacesAndNewlines)
                    if !response.isEmpty {
                        updateAgentMessage(id: agentMsgId, text: response, status: .sent)
                    } else {
                        messages.removeAll { $0.id == agentMsgId }
                    }
                    messageBuffer = ""

                case .error:
                    let errorText = event.displayText
                    updateAgentMessage(id: agentMsgId, text: errorText.isEmpty ? "Error" : errorText, status: .failed)

                case .pipeline, .thinking, .thought, .heartbeat, .card, .artifact,
                     .agentResponse, .userPrompt, .userResponse, .clarificationRequest:
                    break

                case .none:
                    break
                }
            }

            // If stream ended without .done (connection dropped), finalize
            if !messageBuffer.isEmpty {
                let response = messageBuffer.trimmingCharacters(in: .whitespacesAndNewlines)
                if !response.isEmpty {
                    updateAgentMessage(id: agentMsgId, text: response, status: .sent)
                }
            }

        } catch {
            updateAgentMessage(id: agentMsgId, text: "Connection error. Try again.", status: .failed)
        }

        isStreaming = false
    }

    private func updateAgentMessage(id: String, text: String, status: MessageStatus) {
        if let index = messages.firstIndex(where: { $0.id == id }) {
            messages[index] = ChatMessage(
                id: id,
                content: .text(text),
                author: .agent,
                status: status
            )
        }
    }
}
