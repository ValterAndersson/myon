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

    var body: some View {
        VStack(spacing: Space.md) {
            if !vm.errorMessage.orEmpty.isEmpty {
                Banner(title: "Error", message: vm.errorMessage, kind: .error)
            }
            if let ctx = entryContext, !ctx.isEmpty { Banner(title: "Requested", message: ctx, kind: .info) }
            PinnedRailView(cards: pinned) { _ in }
            UpNextRailView(cards: vm.cards, upNextIds: vm.upNext) { _ in }
            ScrollView {
                CanvasGridView(cards: vm.cards, columns: 12, onAccept: { cardId in
                    guard let cid = vm.canvasId ?? canvasId else { return }
                    Task { await vm.applyAction(canvasId: cid, type: "ACCEPT_PROPOSAL", cardId: cardId) }
                }, onReject: { cardId in
                    guard let cid = vm.canvasId ?? canvasId else { return }
                    Task { await vm.applyAction(canvasId: cid, type: "REJECT_PROPOSAL", cardId: cardId) }
                })
                    .padding(InsetsToken.screen)
            }
        }
        .environment(\.cardActionHandler, handleCardAction)
        .sheet(isPresented: $showRefine) { RefineSheet(text: $refineText) { _ in showRefine = false } }
        .sheet(isPresented: $showSwap) { SwapSheet { _, _ in showSwap = false } }
        .overlay {
            if vm.showStreamOverlay {
                StreamOverlay(
                    status: vm.currentAgentStatus ?? "Working...",
                    isThinking: vm.isAgentThinking,
                    events: vm.streamEvents
                )
            }
        }
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
        .onChange(of: vm.canvasId) { newValue in
            guard !didInvokeAgent, let cid = newValue else { return }
            if let msg = computeAgentMessage(from: entryContext) {
                didInvokeAgent = true
                let correlationId = UUID().uuidString
                
                // Start SSE stream - this will both stream events AND invoke the agent
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
                withAnimation { vm.cards.insert(CanvasCardModel(type: .summary, data: .inlineInfo("The agent chose this based on your recent volume and preferences."), width: .oneHalf), at: 0) }
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


