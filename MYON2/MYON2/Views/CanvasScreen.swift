import SwiftUI

struct CanvasScreen: View {
    @StateObject private var vm = CanvasViewModel()
    let userId: String
    let canvasId: String?
    let purpose: String?
    let entryContext: String?
    @State private var seededDemo: Bool = false
    @State private var showRefine: Bool = false
    @State private var refineText: String = ""
    @State private var showSwap: Bool = false
    @State private var pinned: [CanvasCardModel] = []
    @State private var toastText: String? = nil
    @State private var didInvokeAgent: Bool = false
    @State private var composerText: String = ""
    @State private var answeredClarifications: Set<String> = []
    
    private typealias ClarificationPrompt = TimelineClarificationPrompt

    var body: some View {
        let embeddedCards = vm.cards.sorted {
            ($0.publishedAt ?? Date.distantPast) < ($1.publishedAt ?? Date.distantPast)
        }
        let pendingClarification = activeClarificationPrompt
        
        VStack(spacing: 0) {
            if !vm.errorMessage.orEmpty.isEmpty {
                Banner(title: "Error", message: vm.errorMessage, kind: .error)
            }
            WorkspaceTimelineView(
                events: vm.workspaceEvents,
                embeddedCards: embeddedCards,
                syntheticClarification: syntheticClarificationPrompt,
                answeredClarifications: answeredClarifications,
                onClarificationSubmit: handleClarificationSubmit,
                onClarificationSkip: handleClarificationSkip
            )
            composeBar(pendingClarification: pendingClarification)
        }
        .environment(\.cardActionHandler, handleCardAction)
        .sheet(isPresented: $showRefine) { RefineSheet(text: $refineText) { _ in showRefine = false } }
        .sheet(isPresented: $showSwap) { SwapSheet { _, _ in showSwap = false } }
        .navigationTitle("Canvas")
        .onAppear {
            if let cid = canvasId {
                vm.start(userId: userId, canvasId: cid)
            } else {
                let p = purpose ?? "ad_hoc"
                vm.start(userId: userId, purpose: p)
            }
        }
        .onDisappear { vm.stop() }
        .onChange(of: vm.isReady) { ready in
            guard ready, !didInvokeAgent, let cid = vm.canvasId else { return }
            if let msg = computeAgentMessage(from: entryContext) {
                didInvokeAgent = true
                vm.clearCards()
                answeredClarifications.removeAll()
                let correlationId = UUID().uuidString
                vm.startSSEStream(userId: userId, canvasId: cid, message: msg, correlationId: correlationId)
            }
        }
        .overlay(alignment: .bottom) {
            if let t = toastText {
                UndoToast(t) {
                    if let cid = vm.canvasId ?? canvasId {
                        Task { await vm.applyAction(canvasId: cid, type: "UNDO", cardId: nil) }
                    }
                    toastText = nil
                }
                .padding(.bottom, Space.xl)
            }
        }
        .overlay {
            if !vm.isReady {
                ZStack {
                    ColorsToken.Background.primary.opacity(0.6).ignoresSafeArea()
                    VStack(spacing: Space.md) {
                        ProgressView().progressViewStyle(.circular)
                        MyonText("Connecting to canvas…", style: .subheadline, color: ColorsToken.Text.secondary)
                    }
                    .padding(InsetsToken.screen)
                }
            }
        }
        .overlay {
            if vm.isApplying {
                ZStack {
                    Color.black.opacity(0.05).ignoresSafeArea()
                    ProgressView().progressViewStyle(.circular)
                }
                .allowsHitTesting(true)
            }
        }
    }
}

private extension Optional where Wrapped == String {
    var orEmpty: String { self ?? "" }
}

// MARK: - Demo seeding (disabled; live data now)
extension CanvasScreen {
    private func composeBar(pendingClarification: ClarificationPrompt?) -> some View {
        let placeholder = pendingClarification?.question ?? "Ask anything…"
        return HStack(spacing: Space.sm) {
            TextField(placeholder, text: $composerText, axis: .vertical)
                .lineLimit(1...4)
                .padding(Space.sm)
                .background(ColorsToken.Surface.default.opacity(0.6))
                .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.medium, style: .continuous))
            Button(action: sendComposerMessage) {
                Image(systemName: "paperplane.fill")
                    .foregroundColor(.white)
                    .padding(Space.sm)
                    .background(composerText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? ColorsToken.Text.secondary : ColorsToken.Brand.primary)
                    .clipShape(Circle())
            }
            .disabled(composerText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
        }
        .padding(.horizontal, Space.lg)
        .padding(.bottom, Space.md)
    }
    
    private func sendComposerMessage() {
        let trimmed = composerText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        if let pending = activeClarificationPrompt {
            composerText = ""
            handleClarificationSubmit(id: pending.id, question: pending.question, answer: trimmed)
            return
        }
        composerText = ""
        firePrompt(trimmed)
    }
    
    private func firePrompt(_ message: String, resetCards: Bool = true) {
        guard let cid = vm.canvasId ?? canvasId else { return }
        if resetCards {
            answeredClarifications.removeAll()
            vm.clearCards()
        }
        let correlationId = UUID().uuidString
        vm.startSSEStream(userId: userId, canvasId: cid, message: message, correlationId: correlationId)
    }
    
    private func handleClarificationSubmit(id: String, question: String, answer: String) {
        answeredClarifications.insert(id)
        vm.clearPendingClarification(id: id)
        let message = "Clarification response — \(question): \(answer)"
        vm.logUserResponse(text: message)
        firePrompt(message, resetCards: false)
    }
    
    private func handleClarificationSkip(id: String, question: String) {
        answeredClarifications.insert(id)
        vm.clearPendingClarification(id: id)
        let message = "Clarification skipped — \(question)"
        vm.logUserResponse(text: message)
        firePrompt(message, resetCards: false)
    }
    
    private var handleCardAction: CardActionHandler {
        { action, card in
            switch action.kind {
            case "refine":
                refineText = ""; showRefine = true
            case "swap":
                showSwap = true
            case "copy":
                UIPasteboard.general.string = card.title ?? ""
            case "apply":
                if let cid = vm.canvasId ?? canvasId {
                    Task { await vm.applyAction(canvasId: cid, type: "ACCEPT_PROPOSAL", cardId: card.id) }
                    toastText = "Applied"
                }
            case "dismiss":
                if let cid = vm.canvasId ?? canvasId {
                    Task { await vm.applyAction(canvasId: cid, type: "REJECT_PROPOSAL", cardId: card.id) }
                    toastText = "Dismissed"
                }
            case "accept_all":
                if let groupId = card.meta?.groupId, let cid = vm.canvasId ?? canvasId {
                    Task { await vm.applyAction(canvasId: cid, type: "ACCEPT_ALL", cardId: nil, payload: ["group_id": AnyCodable(groupId)]) }
                    toastText = "Applied group"
                }
            case "reject_all":
                if let groupId = card.meta?.groupId, let cid = vm.canvasId ?? canvasId {
                    Task { await vm.applyAction(canvasId: cid, type: "REJECT_ALL", cardId: nil, payload: ["group_id": AnyCodable(groupId)]) }
                    toastText = "Dismissed group"
                }
            case "pin":
                if !pinned.contains(where: { $0.id == card.id }) { pinned.append(card) }
            case "unpin":
                pinned.removeAll { $0.id == card.id }
            case "explain":
                withAnimation {
                    vm.cards.insert(
                        CanvasCardModel(
                            type: .summary,
                            data: .inlineInfo("The agent chose this based on your recent volume and preferences."),
                            width: .oneHalf,
                            publishedAt: Date()
                        ),
                        at: 0
                    )
                }
            default:
                break
            }
        }
    }
    private func computeAgentMessage(from ctx: String?) -> String? {
        guard let ctx, !ctx.isEmpty else { return nil }
        if ctx.hasPrefix("freeform:") {
            return String(ctx.dropFirst("freeform:".count))
        }
        if ctx.hasPrefix("quick:") {
            let key = String(ctx.dropFirst("quick:".count)).lowercased()
            if key.contains("plan program") { return "Take a look at my profile and goals and propose a training program well suited for me, relying on defined exercise science." }
            if key.contains("new workout") { return "I want to train today. Plan an upper body session and propose the first target." }
            if key.contains("analyze progress") { return "Analyze my progress and show a few key charts for the last 6 weeks." }
        }
        return ctx
    }
}

private extension CanvasScreen {
    private var workspaceClarificationPrompt: ClarificationPrompt? {
        for entry in vm.workspaceEvents.reversed() {
            guard entry.event.eventType == .clarificationRequest,
                  let id = entry.event.content?["id"]?.value as? String,
                  answeredClarifications.contains(id) == false,
                  let question = entry.event.content?["question"]?.value as? String else { continue }
            return ClarificationPrompt(id: id, question: question)
        }
        return nil
    }
    
    private var syntheticClarificationPrompt: WorkspaceTimelineView.ClarificationPrompt? {
        guard let cue = vm.pendingClarificationCue else { return nil }
        if let workspace = workspaceClarificationPrompt, workspace.id == cue.id {
            return nil
        }
        return WorkspaceTimelineView.ClarificationPrompt(id: cue.id, question: cue.question)
    }
    
    private var activeClarificationPrompt: ClarificationPrompt? {
        workspaceClarificationPrompt ?? syntheticClarificationPrompt
    }
}


