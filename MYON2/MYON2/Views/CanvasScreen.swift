import SwiftUI

struct CanvasScreen: View {
    @StateObject private var vm = CanvasViewModel()
    @StateObject private var streamer = DirectStreamingService()
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
    @State private var didStartStream: Bool = false
    @State private var sreActive: Bool = false
    @State private var sreStatus: String? = nil
    @State private var sreCorrelationId: String? = nil

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
            guard !didStartStream, let cid = newValue else { return }
            if let msg = computeAgentMessage(from: entryContext) {
                didStartStream = true
                sreActive = true
                let corr = UUID().uuidString
                sreCorrelationId = corr
                sreStatus = "Understanding task"
                streamer.streamQuery(
                    message: msg,
                    userId: userId,
                    sessionId: nil,
                    canvasId: cid,
                    correlationId: corr,
                    progressHandler: { _, action in
                        if let a = action, !a.isEmpty {
                            DispatchQueue.main.async { self.sreStatus = a }
                        }
                    },
                    completion: { _ in
                        // Keep overlay until cards arrive; completion just ends the stream
                    }
                )
            }
        }
        .onChange(of: vm.cards.count) { newCount in
            if newCount > 0 { sreActive = false }
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
        .overlay(alignment: .top) {
            if sreActive, let status = sreStatus, vm.cards.isEmpty {
                VStack {
                    HStack {
                        ProgressView().progressViewStyle(.circular)
                        MyonText(status, style: .subheadline, color: ColorsToken.Text.secondary)
                    }
                    .padding(8)
                    .background(ColorsToken.Background.secondary.opacity(0.8))
                    .cornerRadius(8)
                    Spacer()
                }
                .padding(InsetsToken.screen)
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
            case "submit":
                // Handle clarify questions submission
                print("[CanvasScreen] Handling submit action for card: \(card.id)")
                if let cid = vm.canvasId ?? canvasId {
                    Task {
                        await vm.sendResponseToAgent(
                            canvasId: cid,
                            cardId: card.id,
                            response: action.payload ?? [:]
                        )
                        toastText = "Response sent"
                    }
                }
            case "skip":
                // Handle skip action
                print("[CanvasScreen] Handling skip action for card: \(card.id)")
                if let cid = vm.canvasId ?? canvasId {
                    Task {
                        await vm.sendResponseToAgent(
                            canvasId: cid,
                            cardId: card.id,
                            response: action.payload ?? [:]
                        )
                        toastText = "Skipped"
                    }
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


