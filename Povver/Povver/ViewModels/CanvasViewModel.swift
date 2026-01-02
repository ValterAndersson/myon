/**
 =============================================================================
 CanvasViewModel.swift - Central Canvas State Management
 =============================================================================
 
 PURPOSE:
 The central ViewModel for the canvas experience. Manages canvas state, card
 collections, SSE streaming from agent, and user actions.
 
 ARCHITECTURE CONTEXT:
 ┌─────────────────────────────────────────────────────────────────────────────┐
 │ iOS CANVAS DATA FLOW                                                        │
 │                                                                             │
 │ CanvasScreen.swift (UI)                                                     │
 │   │                                                                         │
 │   ▼                                                                         │
 │ CanvasViewModel (THIS FILE)                                                 │
 │   │                                                                         │
 │   ├──▶ CanvasRepository.subscribe() ──▶ Firestore Listener                 │
 │   │      cards collection, state doc                                        │
 │   │                                                                         │
 │   ├──▶ CanvasService.applyAction() ──▶ apply-action.js                     │
 │   │      user actions (accept, dismiss, edit)                               │
 │   │                                                                         │
 │   ├──▶ DirectStreamingService.streamQuery() ──▶ stream-agent-normalized.js │
 │   │      SSE events during agent work                                       │
 │   │                                                                         │
 │   └──▶ CanvasService.openCanvas() ──▶ open-canvas.js                       │
 │          canvas + session initialization                                    │
 └─────────────────────────────────────────────────────────────────────────────┘
 
 KEY STATE:
 - cards: [CanvasCardModel] - All canvas cards from Firestore listener
 - streamEvents: [StreamEvent] - SSE events for workspace timeline
 - workspaceEvents: [WorkspaceEvent] - Persisted conversation history
 - progressState: AgentProgressState - Monotonic progress tracking for UX
 - pendingClarificationCue: ClarificationCue? - Pending agent question
 
 METHODS:
 - start(userId:canvasId:) - Open existing canvas with session reuse
 - start(userId:purpose:) - Create new canvas with combined openCanvas call
 - startSSEStream() - Begin agent streaming with correlation ID
 - applyAction() - Send user action to apply-action.js
 - handleIncomingStreamEvent() - Process SSE events and update UI
 
 FIRESTORE LISTENERS:
 - Canvas cards: users/{uid}/canvases/{canvasId}/cards
 - Canvas state: users/{uid}/canvases/{canvasId}/state
 - Workspace entries: users/{uid}/canvases/{canvasId}/workspace_entries
 - Events (telemetry): users/{uid}/canvases/{canvasId}/events
 
 RELATED FILES:
 - CanvasScreen.swift: UI layer that uses this ViewModel
 - CanvasRepository.swift: Firestore subscription logic
 - CanvasService.swift: HTTP calls to Firebase Functions
 - DirectStreamingService.swift: SSE streaming client
 
 =============================================================================
 */

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
    
    // Monotonic progress tracking (Phase 1 UX Polish)
    @Published var progressState = AgentProgressState()

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
        let startTime = Date()
        
        // Start session logging
        SessionLogger.shared.startSession(userId: userId, canvasId: canvasId)
        SessionLogger.shared.log(.canvas, .info, "Canvas start BEGIN (existing canvas)", context: ["canvas_id": canvasId])
        
        streamTask = Task { [weak self] in
            guard let self = self else { return }
            do {
                self.currentUserId = userId
                self.canvasId = canvasId
                await MainActor.run { CanvasRepository.shared.currentCanvasId = canvasId }
                
                // PHASE 1 OPTIMIZATION: Clear UI state and attach listeners IMMEDIATELY
                await MainActor.run {
                    self.cards = []
                    self.upNext = []
                    self.pendingClarificationCue = nil
                }
                
                // Attach listeners right away (don't wait for session)
                self.attachEventsListener(userId: userId, canvasId: canvasId)
                self.attachWorkspaceEntriesListener(userId: userId, canvasId: canvasId)
                let elapsed = String(format: "%.2f", Date().timeIntervalSince(startTime))
                SessionLogger.shared.log(.canvas, .debug, "Listeners attached", context: ["elapsed_s": elapsed])
                
                // PHASE 1 OPTIMIZATION: Start session initialization in parallel
                // Use forceNew: false to enable session reuse
                let sessionTask = Task<String?, Never> {
                    let sessionStart = Date()
                    do {
                        let sessionId = try await self.service.initializeSession(canvasId: canvasId, purpose: "general", forceNew: false)
                        let sessionDuration = Date().timeIntervalSince(sessionStart)
                        SessionLogger.shared.updateContext(sessionId: sessionId)
                        SessionLogger.shared.log(.canvas, .info, "Session initialized", context: [
                            "session_id": sessionId,
                            "duration_s": String(format: "%.2f", sessionDuration),
                            "reuse_enabled": true
                        ])
                        return sessionId
                    } catch {
                        SessionLogger.shared.logError(
                            category: .canvas,
                            message: "initializeSession failed - will create new on first message",
                            error: error
                        )
                        return nil
                    }
                }
                
                // PHASE 1 OPTIMIZATION: Skip purgeCanvas
                // Purging workspace_entries on every open adds latency and loses conversation history
                SessionLogger.shared.log(.canvas, .debug, "Skipping purgeCanvas (optimization)")
                
                let subElapsed = String(format: "%.2f", Date().timeIntervalSince(startTime))
                SessionLogger.shared.log(.canvas, .debug, "Starting subscription", context: ["elapsed_s": subElapsed])
                
                // Subscribe to canvas updates
                var firstSnapshotReceived = false
                for try await snap in self.repo.subscribe(userId: userId, canvasId: canvasId) {
                    if !firstSnapshotReceived {
                        firstSnapshotReceived = true
                        let snapElapsed = String(format: "%.2f", Date().timeIntervalSince(startTime))
                        SessionLogger.shared.log(.canvas, .info, "First snapshot received", context: ["elapsed_s": snapElapsed])
                    }
                    
                    // Log canvas state snapshot
                    self.logCanvasSnapshot(snap: snap, trigger: "firestore_update")
                    
                    self.version = snap.version
                    self.cards = snap.cards
                    self.upNext = snap.upNext
                    if let ph = snap.state.phase { self.phase = ph }
                    
                    // Mark ready on first snapshot
                    if self.isReady == false {
                        self.isReady = true
                        let readyElapsed = String(format: "%.2f", Date().timeIntervalSince(startTime))
                        SessionLogger.shared.log(.canvas, .info, "Canvas READY", context: ["elapsed_s": readyElapsed])
                    }
                }
                
                // Resolve session in background (don't block UI)
                if let sessionId = await sessionTask.value {
                    await MainActor.run { self.currentSessionId = sessionId }
                }
                
            } catch {
                self.errorMessage = error.localizedDescription
                SessionLogger.shared.logError(category: .canvas, message: "Canvas subscribe error", error: error)
            }
        }
    }

    func start(userId: String, purpose: String) {
        streamTask?.cancel()
        let startTime = Date()
        
        // Start session logging
        SessionLogger.shared.startSession(userId: userId)
        SessionLogger.shared.log(.canvas, .info, "Canvas start BEGIN (new canvas)", context: ["purpose": purpose])
        
        streamTask = Task { [weak self] in
            guard let self = self else { return }
            do {
                self.currentUserId = userId
                
                // PHASE 2 OPTIMIZATION: Use combined openCanvas endpoint (1 call instead of 2)
                // This creates canvas + session in parallel on the server, saving a network round trip
                let openStart = Date()
                let (cid, sessionId) = try await self.service.openCanvas(userId: userId, purpose: purpose)
                let openDuration = Date().timeIntervalSince(openStart)
                
                // Update session context with canvas and session IDs
                SessionLogger.shared.updateContext(canvasId: cid, sessionId: sessionId)
                SessionLogger.shared.log(.canvas, .info, "openCanvas completed", context: [
                    "canvas_id": cid,
                    "session_id": sessionId,
                    "duration_s": String(format: "%.2f", openDuration)
                ])
                
                self.canvasId = cid
                self.currentSessionId = sessionId
                await MainActor.run { CanvasRepository.shared.currentCanvasId = cid }
                
                // Clear UI state and attach listeners IMMEDIATELY
                await MainActor.run {
                    self.cards = []
                    self.upNext = []
                    self.pendingClarificationCue = nil
                }
                
                // Attach listeners right away
                self.attachEventsListener(userId: userId, canvasId: cid)
                self.attachWorkspaceEntriesListener(userId: userId, canvasId: cid)
                let elapsed = String(format: "%.2f", Date().timeIntervalSince(startTime))
                SessionLogger.shared.log(.canvas, .debug, "Listeners attached", context: ["elapsed_s": elapsed])
                
                let subElapsed = String(format: "%.2f", Date().timeIntervalSince(startTime))
                SessionLogger.shared.log(.canvas, .debug, "Starting subscription", context: ["elapsed_s": subElapsed])
                
                // Subscribe to canvas updates
                var firstSnapshotReceived = false
                for try await snap in self.repo.subscribe(userId: userId, canvasId: cid) {
                    if !firstSnapshotReceived {
                        firstSnapshotReceived = true
                        let snapElapsed = String(format: "%.2f", Date().timeIntervalSince(startTime))
                        SessionLogger.shared.log(.canvas, .info, "First snapshot received", context: ["elapsed_s": snapElapsed])
                    }
                    
                    // Log canvas state snapshot
                    self.logCanvasSnapshot(snap: snap, trigger: "firestore_update")
                    
                    self.version = snap.version
                    self.cards = snap.cards
                    self.upNext = snap.upNext
                    if let ph = snap.state.phase { self.phase = ph }
                    
                    // Mark ready on first snapshot
                    if self.isReady == false {
                        self.isReady = true
                        let readyElapsed = String(format: "%.2f", Date().timeIntervalSince(startTime))
                        SessionLogger.shared.log(.canvas, .info, "Canvas READY", context: ["elapsed_s": readyElapsed])
                    }
                }
                
            } catch {
                self.errorMessage = error.localizedDescription
                SessionLogger.shared.logError(category: .canvas, message: "openCanvas/subscribe error", error: error)
            }
        }
    }

    func stop() {
        streamTask?.cancel()
        streamTask = nil
        eventsListener?.remove()
        eventsListener = nil
        workspaceListener?.remove()
        workspaceListener = nil
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
        DebugLogger.log(.canvas, "SSE stream BEGIN: corr=\(correlationId) sessionId=\(currentSessionId ?? "nil")")
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
                // Reset progress state for new work (Phase 1 UX Polish)
                self.progressState.reset()
                self.progressState.advance(to: .understanding)
            }
            
            // Track last meaningful event time for timeout detection
            var lastMeaningfulEventTime = Date()
            let streamTimeoutSeconds: TimeInterval = 120
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
            streamEvents.append(event)
            
        case .toolRunning:
            currentAgentStatus = event.displayText
            isAgentThinking = true
            let toolName = (event.content?["tool"]?.value as? String) ?? (event.content?["tool_name"]?.value as? String) ?? "tool"
            toolStartByName[toolName] = event.timestamp ?? now
            if let phase = event.content?["phase"]?.value as? String {
                progressState.advance(toPhase: phase)
            } else {
                progressState.advance(with: toolName)
            }
            streamEvents.append(event)
            
        case .toolComplete:
            isAgentThinking = false
            let toolName = (event.content?["tool"]?.value as? String) ?? (event.content?["tool_name"]?.value as? String) ?? "tool"
            let start = toolStartByName.removeValue(forKey: toolName) ?? (event.timestamp ?? now)
            let end = event.timestamp ?? now
            let secs = max(0, end - start)
            let formatted = StreamEvent(
                type: "toolComplete",
                agent: event.agent,
                content: [
                    "text": AnyCodable(event.displayText),
                    "tool": AnyCodable(toolName),
                    "duration_s": AnyCodable(secs),
                    "phase": event.content?["phase"] ?? AnyCodable("")
                ],
                timestamp: event.timestamp ?? now,
                metadata: event.metadata
            )
            streamEvents.append(formatted)
            
        case .message:
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
            progressState.complete()
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
            streamEvents.append(event)
            
        case .thought:
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
        eventsListener = eventsRef.addSnapshotListener { snap, _ in
            guard let docs = snap?.documents else { return }
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
    
    // MARK: - Canvas State Snapshot Logging
    
    private func logCanvasSnapshot(snap: CanvasSnapshot, trigger: String) {
        let cardTuples: [(id: String, type: String, status: String, title: String?)] = snap.cards.map { card in
            // Use card.title if available, otherwise extract from data
            let title: String? = card.title ?? card.subtitle
            return (id: card.id, type: card.type.rawValue, status: card.status.rawValue, title: title)
        }
        
        SessionLogger.shared.logCanvasSnapshot(
            phase: snap.state.phase?.rawValue ?? "unknown",
            version: snap.version,
            cards: cardTuples,
            upNext: snap.upNext,
            trigger: trigger
        )
    }
}
