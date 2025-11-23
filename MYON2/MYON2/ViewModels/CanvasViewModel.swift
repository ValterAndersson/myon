import Foundation
import Combine
import FirebaseFirestore

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

    private let repo: CanvasRepositoryProtocol
    private let service: CanvasServiceProtocol
    private var streamTask: Task<Void, Never>?
    private var sseStreamTask: Task<Void, Never>?
    private var cancellables: Set<AnyCancellable> = []
    private var eventsListener: ListenerRegistration?
    
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
                self.canvasId = canvasId
                await MainActor.run { CanvasRepository.shared.currentCanvasId = canvasId }
                self.isReady = false
                self.attachEventsListener(userId: userId, canvasId: canvasId)
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
                let cid = try await self.service.bootstrapCanvas(for: userId, purpose: purpose)
                self.canvasId = cid
                await MainActor.run { CanvasRepository.shared.currentCanvasId = cid }
                self.isReady = false
                self.attachEventsListener(userId: userId, canvasId: cid)
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
        isReady = false
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
        print("[CanvasVM] startSSEStream called userId=\(userId) canvasId=\(canvasId) correlationId=\(correlationId)")
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
                print("[CanvasVM] SSE overlay shown")
            }
            
            do {
                print("[CanvasVM] Starting SSE stream consumption...")
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
                // Stream agent events
                for try await event in DirectStreamingService.shared.streamQuery(
                    userId: userId,
                    canvasId: canvasId,
                    message: message,
                    correlationId: correlationId
                ) {
                    print("[CanvasVM] Received SSE event: \(event.type)")
                    await MainActor.run {
                        // Process stream event
                        self.handleIncomingStreamEvent(event)
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
        case .userPrompt:
            // Show user prompt line in the log
            streamEvents.append(event)
        case .agentResponse:
            // Show agent's final response line
            streamEvents.append(event)
        case .thought:
            // Show synthesized thought duration line
            streamEvents.append(event)
        case .heartbeat, .card:
            break
        }
        
        // Auto-hide overlay if cards start appearing
        if !cards.isEmpty {
            showStreamOverlay = false
        }
    }
    
    private func humanReadableToolName(_ name: String) -> String {
        switch name {
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
                    print("[CanvasTelemetry] event=\(doc.data()["type"] as? String ?? "?") correlation=\(correlation)")
                    DebugLogger.debug(.canvas, "event=\(doc.data()["type"] as? String ?? "?") correlation=\(correlation)")
                }
            }
        }
    }
}


