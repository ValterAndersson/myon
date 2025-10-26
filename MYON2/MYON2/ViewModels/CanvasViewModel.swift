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
    @Published var currentToolCall: (name: String, status: String)? = nil
    @Published var agentThinking: String? = nil

    private let repo: CanvasRepositoryProtocol
    private let service: CanvasServiceProtocol
    private var streamTask: Task<Void, Never>?
    private var cancellables: Set<AnyCancellable> = []
    private var eventsListener: ListenerRegistration?

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
                    // If we have a pending orchestrator invoke, fire once when ready
                    if let staged = PendingAgentInvoke.shared.take() {
                        // SSE now handles publish; do not call invokeCanvasOrchestrator here
                    } else if let pending = self.pendingInvoke {
                        self.pendingInvoke = nil
                        // SSE now handles publish; do not call invokeCanvasOrchestrator here
                    }
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
                    if let staged = PendingAgentInvoke.shared.take() {
                        try? await AgentsApi.invokeCanvasOrchestrator(AgentInvokeRequest(userId: userId, canvasId: cid, message: staged.message, correlationId: staged.correlationId))
                    } else if let pending = self.pendingInvoke {
                        self.pendingInvoke = nil
                        try? await AgentsApi.invokeCanvasOrchestrator(AgentInvokeRequest(userId: userId, canvasId: cid, message: pending.message, correlationId: pending.correlationId))
                    }
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
    func sendResponseToAgent(canvasId: String, cardId: String, response: [String: String]) async {
        do {
            let req = AgentResponseRequest(
                canvasId: canvasId,
                cardId: cardId,
                response: response
            )
            try await AgentsApi.respondToAgent(req)
            DebugLogger.log(.canvas, "Response sent to agent for card: \(cardId)")
        } catch {
            DebugLogger.log(.canvas, "Failed to send response: \(error)")
        }
    }
    
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


