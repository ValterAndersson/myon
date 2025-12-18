import Foundation
import Combine
import FirebaseFirestore

struct ClarificationCue: Identifiable, Equatable {
    let id: String
    let question: String
}

@MainActor
final class CanvasViewModel: ObservableObject {
    @Published var cards: [CanvasCardModel] = []
    @Published var upNext: [String] = []
    @Published var version: Int = 0
    @Published var phase: CanvasPhase = .planning
    @Published var canvasId: String?
    @Published var isApplying: Bool = false
    @Published var errorMessage: String?
    @Published var isReady: Bool = false
    @Published var pendingInvoke: (message: String, correlationId: String)? = nil
    
    // SSE Streaming properties
    @Published var streamEvents: [StreamEvent] = []
    @Published var currentAgentStatus: String? = nil
    @Published var isAgentThinking: Bool = false
    @Published var showStreamOverlay: Bool = false
    @Published var workspaceEvents: [WorkspaceEvent] = []
    @Published var pendingClarificationCue: ClarificationCue? = nil

    private let repo: CanvasRepositoryProtocol
    private let service: CanvasServiceProtocol
    private var streamTask: Task<Void, Never>?
    private var sseStreamTask: Task<Void, Never>?
    private var cancellables: Set<AnyCancellable> = []
    private var eventsListener: ListenerRegistration?
    private var workspaceListener: ListenerRegistration?
    private var currentUserId: String?
    private var currentSessionId: String?
    
    // Overlay synthesis state
    private var messageBuffer: String = ""
    private var thoughtStartAt: Double? = nil
    private var toolStartByName: [String: Double] = [:]

    init(repo: CanvasRepositoryProtocol = CanvasRepository(), service: CanvasServiceProtocol = CanvasService()) {
        self.repo = repo
        self.service = service
    }

    func start(userId: String, canvasId: String) {
        streamTask?.cancel()
        streamTask = Task { [weak self] in
            guard let self = self else { return }
            do {
                self.currentUserId = userId
                self.canvasId = canvasId
                await MainActor.run { CanvasRepository.shared.currentCanvasId = canvasId }
                
                // Initialize session (will reuse existing if valid)
                do {
                    let sessionId = try await self.service.initializeSession(canvasId: canvasId, purpose: "general")
                    await MainActor.run { self.currentSessionId = sessionId }
                    DebugLogger.log(.canvas, "Session initialized: \(sessionId)")
                } catch {
                    DebugLogger.error(.canvas, "initializeSession failed: \(error.localizedDescription) - will create new on first message")
                }
                
                do {
                    try await self.service.purgeCanvas(userId: userId, canvasId: canvasId, dropEvents: true, dropState: false, dropWorkspace: true)
                } catch {
                    DebugLogger.error(.canvas, "purgeCanvas failed: \(error.localizedDescription)")
                }
                self.isReady = false
                await MainActor.run {
                    self.cards = []
                    self.upNext = []
                    self.pendingClarificationCue = nil
                }
                self.attachEventsListener(userId: userId, canvasId: canvasId)
                self.attachWorkspaceEntriesListener(userId: userId, canvasId: canvasId)
                DebugLogger.log(.canvas, "subscribe: user=\(userId) canvas=\(canvasId)")
                for try await snap in self.repo.subscribe(userId: userId, canvasId: canvasId) {
                    DebugLogger.debug(.canvas, "snapshot: v=\(snap.version) cards=\(snap.cards.count) upNext=\(snap.upNext.count)")
                    self.version = snap.version
                    self.cards = snap.cards
                    self.upNext = snap.upNext
                    if let ph = snap.state.phase { self.phase = ph }
                    if self.isReady == false { self.isReady = true }
                    // Removed duplicate invocation - handled in CanvasScreen.onChange
                }
            } catch {
                self.errorMessage = error.localizedDescription
                DebugLogger.error(.canvas, "subscribe error: \(error.localizedDescription)")
            }
        }
    }

    func start(userId: String, purpose: String) {
        streamTask?.cancel()
        streamTask = Task { [weak self] in
            guard let self = self else { return }
            do {
                self.currentUserId = userId
                let cid = try await self.service.bootstrapCanvas(for: userId, purpose: purpose)
                self.canvasId = cid
                await MainActor.run { CanvasRepository.shared.currentCanvasId = cid }
                
                // Initialize session - FORCE NEW for fresh planning sessions
                // This avoids conversation history contamination from old prompts
                do {
                    let sessionId = try await self.service.initializeSession(canvasId: cid, purpose: purpose, forceNew: true)
                    await MainActor.run { self.currentSessionId = sessionId }
                    DebugLogger.log(.canvas, "Session initialized (forceNew): \(sessionId)")
                } catch {
                    DebugLogger.error(.canvas, "initializeSession failed: \(error.localizedDescription) - will create new on first message")
                }
                
                do {
                    try await self.service.purgeCanvas(userId: userId, canvasId: cid, dropEvents: true, dropState: false, dropWorkspace: true)
                } catch {
                    DebugLogger.error(.canvas, "purgeCanvas failed: \(error.localizedDescription)")
                }
                self.isReady = false
                await MainActor.run {
                    self.cards = []
                    self.upNext = []
                    self.pendingClarificationCue = nil
                }
                self.attachEventsListener(userId: userId, canvasId: cid)
                self.attachWorkspaceEntriesListener(userId: userId, canvasId: cid)
                DebugLogger.log(.canvas, "bootstrapped canvas id=\(cid) purpose=\(purpose)")
                for try await snap in self.repo.subscribe(userId: userId, canvasId: cid) {
                    DebugLogger.debug(.canvas, "snapshot: v=\(snap.version) cards=\(snap.cards.count) upNext=\(snap.upNext.count)")
                    self.version = snap.version
                    self.cards = snap.cards
                    self.upNext = snap.upNext
                    if let ph = snap.state.phase { self.phase = ph }
                    if self.isReady == false { self.isReady = true }
                    // Removed duplicate invocation - handled in CanvasScreen.onChange
                }
            } catch {
                self.errorMessage = error.localizedDescription
                DebugLogger.error(.canvas, "bootstrap/subscribe error: \(error.localizedDescription)")
            }
        }
    }

    func stop() {
        streamTask?.cancel(); streamTask = nil
        eventsListener?.remove(); eventsListener = nil
        workspaceListener?.remove(); workspaceListener = nil
        isReady = false
        currentSessionId = nil
    }

    // MARK: - Actions
    func applyAction(canvasId: String, expectedVersion: Int? = nil, type: String, cardId: String? = nil, payload: [String: AnyCodable]? = nil) async {
        guard !isApplying else { return }
        isApplying = true
        defer { isApplying = false }
        let req = ApplyActionRequestDTO(
            canvasId: canvasId,
            expected_version: expectedVersion ?? version,
            action: CanvasActionDTO(type: type, card_id: cardId, payload: payload, by: "user", idempotency_key: UUID().uuidString)
        )
        do {
            let result = try await service.applyAction(req)
            if result.success == false, let err = result.error {
                if err.code == "STALE_VERSION" {
                    // Retry once with updated version
                    let retry = ApplyActionRequestDTO(canvasId: canvasId, expected_version: self.version, action: req.action)
                    _ = try await service.applyAction(retry)
                } else {
                    errorMessage = err.message
                }
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func startSSEStream(userId: String, canvasId: String, message: String, correlationId: String) {
        DebugLogger.log(.canvas, "startSSEStream: user=\(userId) canvas=\(canvasId) corr=\(correlationId)")
        sseStreamTask?.cancel()
        sseStreamTask = Task { [weak self] in
            guard let self = self else { return }
            
            // Show overlay while agent is working
            await MainActor.run {
                self.showStreamOverlay = true
                self.streamEvents = []
                self.currentAgentStatus = "Connecting..."
                self.isAgentThinking = true
                self.messageBuffer = ""
                self.thoughtStartAt = Date().timeIntervalSince1970
                self.toolStartByName.removeAll()
            }
            
            // Track last meaningful event time for timeout detection
            var lastMeaningfulEventTime = Date()
            let streamTimeoutSeconds: TimeInterval = 30 // Timeout after 30s of only heartbeats
            var receivedDoneEvent = false
            
            do {
                // Seed log with user prompt
                await MainActor.run {
                    let now = Date().timeIntervalSince1970
                    let evt = StreamEvent(
                        type: "user_prompt",
                        agent: "user",
                        content: [
                            "text": AnyCodable(message),
                            "correlation_id": AnyCodable(correlationId)
                        ],
                        timestamp: now,
                        metadata: ["source": AnyCodable("client")] 
                    )
                    self.streamEvents.append(evt)
                }
                self.recordUserPromptEntry(userId: userId, canvasId: canvasId, message: message, correlationId: correlationId)
                // Stream agent events
                for try await event in DirectStreamingService.shared.streamQuery(
                    userId: userId,
                    canvasId: canvasId,
                    message: message,
                    correlationId: correlationId,
                    sessionId: self.currentSessionId
                ) {
                    // Check for timeout (only heartbeats for too long)
                    let isMeaningfulEvent = event.eventType != .heartbeat && event.eventType != .status
                    if isMeaningfulEvent {
                        lastMeaningfulEventTime = Date()
                    } else if Date().timeIntervalSince(lastMeaningfulEventTime) > streamTimeoutSeconds {
                        DebugLogger.debug(.canvas, "Stream timeout - only heartbeats for \(streamTimeoutSeconds)s")
                        await MainActor.run {
                            self.currentAgentStatus = "Request timed out"
                            self.showStreamOverlay = false
                            self.isAgentThinking = false
                        }
                        break
                    }
                    
                    DebugLogger.debug(.canvas, "SSE event: \(event.type)")
                    await MainActor.run {
                        // Process stream event
                        self.handleIncomingStreamEvent(event)
                    }
                    
                    if event.eventType == .done {
                        receivedDoneEvent = true
                    }
                }
                
                // If stream ended without done event, clean up gracefully
                if !receivedDoneEvent {
                    DebugLogger.debug(.canvas, "Stream ended without done event - cleaning up")
                    await MainActor.run {
                        self.showStreamOverlay = false
                        self.isAgentThinking = false
                    }
                }
            } catch {
                await MainActor.run {
                    self.errorMessage = "Streaming error: \(error.localizedDescription)"
                    self.showStreamOverlay = false
                    self.isAgentThinking = false
                }
            }
        }
    }
    
    private func handleIncomingStreamEvent(_ event: StreamEvent) {
        let now = Date().timeIntervalSince1970
        guard let type = event.eventType else { return }
        switch type {
        case .thinking:
            currentAgentStatus = event.displayText
            isAgentThinking = true
            if thoughtStartAt == nil { thoughtStartAt = event.timestamp ?? now }
            // Log a thinking line
            streamEvents.append(event)
        case .toolRunning:
            currentAgentStatus = event.displayText
            isAgentThinking = true
            let toolName = (event.content?["tool"]?.value as? String) ?? (event.content?["tool_name"]?.value as? String) ?? "tool"
            toolStartByName[toolName] = event.timestamp ?? now
            // Replace text with humanized label
            let human = humanReadableToolName(toolName)
            let text = "Looking at \(human)"
            let formatted = StreamEvent(
                type: "toolRunning",
                agent: event.agent,
                content: ["text": AnyCodable(text), "tool": AnyCodable(toolName)],
                timestamp: event.timestamp ?? now,
                metadata: event.metadata
            )
            streamEvents.append(formatted)
        case .toolComplete:
            isAgentThinking = false
            let toolName = (event.content?["tool"]?.value as? String) ?? (event.content?["tool_name"]?.value as? String) ?? "tool"
            let start = toolStartByName.removeValue(forKey: toolName) ?? (event.timestamp ?? now)
            let end = event.timestamp ?? now
            let secs = max(0, end - start)
            let human = humanReadableToolName(toolName)
            let text = String(format: "Looked at %@ (%.1fs)", human, secs)
            let formatted = StreamEvent(
                type: "toolComplete",
                agent: event.agent,
                content: [
                    "text": AnyCodable(text),
                    "tool": AnyCodable(toolName),
                    "duration_s": AnyCodable(secs)
                ],
                timestamp: event.timestamp ?? now,
                metadata: event.metadata
            )
            streamEvents.append(formatted)
        case .message:
            // Accumulate assistant message; defer logging until done
            let delta = event.displayText
            if !delta.isEmpty {
                messageBuffer += delta
            }
        case .status:
            currentAgentStatus = event.displayText
            streamEvents.append(event)
            if let sessionId = event.content?["session_id"]?.value as? String {
                currentSessionId = sessionId
            }
        case .userPrompt:
            streamEvents.append(event)
        case .userResponse:
            streamEvents.append(event)
        case .clarificationRequest:
            streamEvents.append(event)
            if let id = event.content?["id"]?.value as? String,
               let question = event.content?["question"]?.value as? String {
                pendingClarificationCue = ClarificationCue(id: id, question: question)
            }
        case .error:
            errorMessage = event.displayText
            showStreamOverlay = false
            isAgentThinking = false
        case .done:
            // Close any ongoing thinking period
            if let start = thoughtStartAt {
                let secs = max(0, (event.timestamp ?? now) - start)
                let text = String(format: "Thought for %.1fs", secs)
                let thoughtEvt = StreamEvent(
                    type: "thought",
                    agent: event.agent,
                    content: [
                        "text": AnyCodable(text),
                        "duration_s": AnyCodable(secs)
                    ],
                    timestamp: event.timestamp ?? now,
                    metadata: event.metadata
                )
                streamEvents.append(thoughtEvt)
                thoughtStartAt = nil
            }
            isAgentThinking = false
            // Emit the aggregated agent response if any
            let response = messageBuffer.trimmingCharacters(in: .whitespacesAndNewlines)
            if !response.isEmpty {
                let responseEvt = StreamEvent(
                    type: "agent_response",
                    agent: event.agent,
                    content: ["text": AnyCodable(response)],
                    timestamp: event.timestamp ?? now,
                    metadata: event.metadata
                )
                streamEvents.append(responseEvt)
            }
            messageBuffer = ""
            showStreamOverlay = false
        case .agentResponse:
            // Show agent's final response line
            streamEvents.append(event)
        case .thought:
            // Show synthesized thought duration line
            streamEvents.append(event)
        case .card, .heartbeat:
            break
        }
        
        // Auto-hide overlay if cards start appearing
        if !cards.isEmpty {
            showStreamOverlay = false
        }
    }
    
    private func humanReadableToolName(_ name: String) -> String {
        switch name {
        case "tool_set_canvas_context": return "canvas context"
        case "tool_fetch_profile": return "athlete profile"
        case "tool_fetch_recent_sessions": return "recent sessions"
        case "tool_emit_agent_event": return "telemetry"
        case "tool_format_workout_plan_cards": return "workout plan formatter"
        case "tool_format_analysis_cards": return "analysis formatter"
        case "tool_publish_cards": return "card publisher"
        case "get_user_workouts": return "activity history"
        case "get_user_routines": return "routines"
        case "list_exercises", "search_exercises": return "exercise library"
        case "get_user_templates": return "templates"
        case "get_active_workout": return "active workout"
        default: return name.replacingOccurrences(of: "_", with: " ")
        }
    }
    
    private func attachEventsListener(userId: String, canvasId: String) {
        eventsListener?.remove()
        let db = Firestore.firestore()
        let eventsRef = db.collection("users").document(userId).collection("canvases").document(canvasId).collection("events").order(by: "created_at", descending: true).limit(to: 50)
        eventsListener = eventsRef.addSnapshotListener { [weak self] snap, _ in
            guard let docs = snap?.documents else { return }
            // Lightweight telemetry: log correlation id if present
            for doc in docs {
                if let payload = doc.data()["payload"] as? [String: Any], let correlation = payload["correlation_id"] as? String {
                    DebugLogger.debug(.canvas, "event=\(doc.data()["type"] as? String ?? "?") correlation=\(correlation)")
                }
            }
        }
    }

    private func attachWorkspaceEntriesListener(userId: String, canvasId: String) {
        workspaceListener?.remove()
        let db = Firestore.firestore()
        let ref = db.collection("users")
            .document(userId)
            .collection("canvases")
            .document(canvasId)
            .collection("workspace_entries")
            .order(by: "created_at", descending: false)
            .limit(to: 200)
        let decoder = JSONDecoder()
        var hasReceivedServerSnapshot = false
        workspaceListener = ref.addSnapshotListener { [weak self] snapshot, error in
            guard let self, let snapshot = snapshot else { return }
            if snapshot.metadata.isFromCache && !hasReceivedServerSnapshot {
                return
            }
            hasReceivedServerSnapshot = true
            let docs = snapshot.documents
            let events: [WorkspaceEvent] = docs.compactMap { doc in
                guard let entry = doc.data()["entry"] as? [String: Any],
                      JSONSerialization.isValidJSONObject(entry),
                      let data = try? JSONSerialization.data(withJSONObject: entry),
                      let streamEvent = try? decoder.decode(StreamEvent.self, from: data) else {
                    return nil
                }
                let timestamp = (doc.data()["created_at"] as? Timestamp)?.dateValue()
                return WorkspaceEvent(id: doc.documentID, event: streamEvent, createdAt: timestamp)
            }
            Task { @MainActor in
                self.workspaceEvents = events
            }
        }
    }

    private func recordUserPromptEntry(userId: String, canvasId: String, message: String, correlationId: String) {
        let db = Firestore.firestore()
        let ref = db.collection("users")
            .document(userId)
            .collection("canvases")
            .document(canvasId)
            .collection("workspace_entries")
            .document()
        let entry: [String: Any] = [
            "entry": [
                "type": "user_prompt",
                "agent": userId,
                "content": [
                    "text": message,
                    "correlation_id": correlationId
                ],
                "timestamp": Date().timeIntervalSince1970,
                "metadata": [
                    "source": "client"
                ]
            ],
            "type": "user_prompt",
            "agent": userId,
            "correlation_id": correlationId,
            "created_at": FieldValue.serverTimestamp()
        ]
        ref.setData(entry) { error in
            if let error {
                DebugLogger.error(.canvas, "Failed to log prompt entry: \(error.localizedDescription)")
            }
        }
    }

    func clearCards() {
        cards = []
        upNext = []
    }

    func logUserResponse(text: String) {
        guard let userId = currentUserId, let canvasId = canvasId else { return }
        let db = Firestore.firestore()
        let ref = db.collection("users")
            .document(userId)
            .collection("canvases")
            .document(canvasId)
            .collection("workspace_entries")
            .document()
        let entry: [String: Any] = [
            "entry": [
                "type": "user_response",
                "agent": userId,
                "content": [
                    "text": text
                ],
                "timestamp": Date().timeIntervalSince1970
            ],
            "type": "user_response",
            "agent": userId,
            "created_at": FieldValue.serverTimestamp()
        ]
        ref.setData(entry) { error in
            if let error {
                DebugLogger.error(.canvas, "Failed to log user response: \(error.localizedDescription)")
            }
        }
    }

    func clearPendingClarification(id: String) {
        if pendingClarificationCue?.id == id {
            pendingClarificationCue = nil
        }
    }
}
