import SwiftUI

struct ChatHomeView: View {
    let userId: String?
    @State private var query: String = ""
    @State private var navigateToCanvas = false
    @State private var entryContext: String = ""

    private let quickActions: [String] = [
        "Make a training program",
        "Start exercise",
        "Analyze my progress"
    ]

    var body: some View {
        ZStack {
            ColorsToken.Background.primary.ignoresSafeArea()

            VStack(alignment: .center, spacing: Space.xl) {
                header
                inputBar
                quickActionsSection
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .center)
            .frame(maxWidth: LayoutToken.contentMaxWidth)
            .padding(InsetsToken.screen)
        }
        .navigationTitle("")
        .navigationBarTitleDisplayMode(.inline)
        .overlay(NavigationLink(destination: canvasDestination, isActive: $navigateToCanvas) { EmptyView() }.hidden())
    }

    private var header: some View {
        VStack(alignment: .center, spacing: Space.sm) {
            MyonText("What’s on the agenda today?", style: .display, align: .center)
        }
    }

    private var inputBar: some View {
        AgentPromptBar(text: $query, placeholder: "Ask anything") {
            entryContext = "freeform:" + query
            navigateToCanvas = true
            // Fire-and-forget: invoke orchestrator after canvas bootstraps
            Task { await sendToAgentIfPossible(message: query) }
        }
        .frame(maxWidth: 680)
    }

    private var quickActionsSection: some View {
        VStack(alignment: .leading, spacing: Space.md) {
            MyonText("Quick actions", style: .subheadline, color: ColorsToken.Text.secondary)
            let columns = [GridItem(.flexible(), spacing: Space.md), GridItem(.flexible(), spacing: Space.md)]
            LazyVGrid(columns: columns, alignment: .center, spacing: Space.md) {
                QuickActionCard(title: "Plan program", icon: iconForPreset("make a training program")) {
                    entryContext = "quick:Plan program"; navigateToCanvas = true
                    Task {
                        let preset = "Take a look at my profile and goals and propose a training program well suited for me, relying on defined exercise science."
                        await sendToAgentIfPossible(message: preset)
                    }
                }
                QuickActionCard(title: "New workout", icon: iconForPreset("start exercise")) {
                    entryContext = "quick:New workout"; navigateToCanvas = true
                }
                QuickActionCard(title: "Analyze progress", icon: iconForPreset("analyze my progress")) {
                    entryContext = "quick:Analyze progress"; navigateToCanvas = true
                }
            }
        }
        .frame(maxWidth: 820)
    }

    private func greetingTitle() -> String {
        // Placeholder; in future derive first name from profile
        return "Good afternoon!"
    }

    @ViewBuilder private var canvasDestination: some View {
        if let uid = userId {
            // Use purpose-based bootstrap; no fixed canvas id
            CanvasScreen(userId: uid, canvasId: nil, purpose: purposeForEntryContext(entryContext), entryContext: entryContext)
        } else {
            EmptyState(title: "Not signed in", message: "Login to view canvas.")
        }
    }

    private func purposeForEntryContext(_ ctx: String) -> String {
        // Simple mapping: quick and freeform default to ad_hoc; can expand later
        return "ad_hoc"
    }

    private func iconForPreset(_ title: String) -> String {
        switch title.lowercased() {
        case "make a training program": return "figure.strengthtraining.traditional"
        case "start exercise": return "play.fill"
        case "analyze my progress": return "chart.bar"
        default: return "sparkles"
        }
    }

    @MainActor private func sendToAgentIfPossible(message: String) async {
        guard let uid = userId else { return }
        // CanvasScreen will bootstrap and store current canvasId in a central place; use a simple cache/singleton if present
        if let cid = CanvasRepository.shared.currentCanvasId {
            let trimmed = message.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !trimmed.isEmpty else { return }
            try? await AgentsApi.invokeCanvasOrchestrator(.init(userId: uid, canvasId: cid, message: trimmed))
        }
    }
}

#if DEBUG
struct ChatHomeView_Previews: PreviewProvider {
    static var previews: some View {
        NavigationStack { ChatHomeView(userId: "demo-user") }
    }
}
#endif


