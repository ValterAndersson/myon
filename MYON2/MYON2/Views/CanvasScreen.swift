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
    @State private var composerExpanded: Bool = true
    
    private typealias ClarificationPrompt = TimelineClarificationPrompt

    var body: some View {
        // Filter to only show the latest session_plan card (others can accumulate)
        let dedupedCards = deduplicateSessionPlans(vm.cards)
        let embeddedCards = dedupedCards.sorted {
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
                onClarificationSkip: handleClarificationSkip,
                hideThinkingEvents: vm.isAgentThinking && !hasSessionPlanCard  // Hide old SRE stream when showing skeleton
            )
            
            // Show skeleton loader when agent is working and no plan card exists yet
            if vm.isAgentThinking && !hasSessionPlanCard {
                VStack(spacing: Space.sm) {
                    AgentProgressIndicator(progressState: vm.progressState)
                    PlanCardSkeleton()
                }
                .padding(.horizontal, Space.md)
                .padding(.vertical, Space.sm)
                .transition(.opacity)
            }
            
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

// MARK: - Compose Bar
extension CanvasScreen {
    /// Check if there's any session plan card
    private var hasSessionPlanCard: Bool {
        vm.cards.contains { $0.type == .session_plan }
    }
    
    /// Check if there's an active proposed plan (makes it the focal element)
    private var hasProposedPlan: Bool {
        vm.cards.contains { (card: CanvasCardModel) -> Bool in
            card.type == .session_plan && card.status == .proposed
        }
    }
    
    private func composeBar(pendingClarification: ClarificationPrompt?) -> some View {
        let placeholder = pendingClarification?.question ?? "Ask anything…"
        
        // When a plan is focal, show collapsed composer unless expanded
        let showCollapsed = hasProposedPlan && !composerExpanded && composerText.isEmpty
        
        return VStack(spacing: 0) {
            if showCollapsed {
                // Minimal "Ask / Adjust" button
                Button {
                    withAnimation(.easeInOut(duration: 0.2)) {
                        composerExpanded = true
                    }
                } label: {
                    HStack(spacing: Space.sm) {
                        Image(systemName: "bubble.left")
                            .font(.system(size: 13))
                        Text("Ask or adjust...")
                            .font(.system(size: 14, weight: .medium))
                    }
                    .foregroundColor(ColorsToken.Text.secondary)
                    .padding(.horizontal, Space.md)
                    .padding(.vertical, 10)
                    .background(ColorsToken.Surface.default.opacity(0.6))
                    .clipShape(Capsule())
                }
                .buttonStyle(PlainButtonStyle())
                .padding(.bottom, Space.md)
            } else {
                // Full composer
                HStack(spacing: Space.sm) {
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
        }
    }
    
    private func sendComposerMessage() {
        let trimmed = composerText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        if let pending = activeClarificationPrompt {
            composerText = ""
            composerExpanded = false  // Collapse after sending
            handleClarificationSubmit(id: pending.id, question: pending.question, answer: trimmed)
            return
        }
        composerText = ""
        composerExpanded = false  // Collapse after sending
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
            // MARK: - Plan Card Actions
            case "accept_plan":
                if let cid = vm.canvasId ?? canvasId {
                    Task { await vm.applyAction(canvasId: cid, type: "ACCEPT_PROPOSAL", cardId: card.id) }
                    toastText = "Plan accepted"
                }
            case "adjust_plan":
                if let instruction = action.payload?["instruction"],
                   let currentPlan = action.payload?["current_plan"] {
                    let prompt = """
                    User adjustment request: \(instruction)
                    
                    Current plan:
                    \(currentPlan)
                    
                    Please update the plan accordingly and publish the revised workout.
                    """
                    firePrompt(prompt, resetCards: false)
                }
            case "swap_exercise":
                if let instruction = action.payload?["instruction"],
                   let currentPlan = action.payload?["current_plan"] {
                    let prompt = """
                    User swap request: \(instruction)
                    
                    Current plan (with any user modifications):
                    \(currentPlan)
                    
                    Please swap the exercise and publish the updated plan.
                    """
                    firePrompt(prompt, resetCards: false)
                }
            // learn_exercise is now handled directly in SessionPlanCard via ExerciseDetailSheet
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
    /// Deduplicate session_plan cards - only show the latest one
    /// Other card types pass through as-is
    func deduplicateSessionPlans(_ cards: [CanvasCardModel]) -> [CanvasCardModel] {
        // Find all session_plan cards sorted by publishedAt (newest first)
        let sessionPlans = cards
            .filter { $0.type == .session_plan }
            .sorted { ($0.publishedAt ?? .distantPast) > ($1.publishedAt ?? .distantPast) }
        
        // Keep only the latest session_plan
        let latestPlanId = sessionPlans.first?.id
        
        // Return all cards except older session_plans
        return cards.filter { card in
            if card.type == .session_plan {
                return card.id == latestPlanId
            }
            return true
        }
    }
    
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
