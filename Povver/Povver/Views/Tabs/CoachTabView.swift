import SwiftUI

/// Coach Tab - Primary agent interface with quick action buttons
/// Direct access to different coaching use-cases without mode switching
struct CoachTabView: View {
    /// Callback to switch to another tab (e.g., Train)
    let switchToTab: (MainTab) -> Void
    
    /// Navigation state for canvas screen
    @State private var navigateToCanvas = false
    @State private var entryContext: String = ""
    @State private var query: String = ""
    
    var body: some View {
        ScrollView {
            VStack(alignment: .center, spacing: Space.xl) {
                Spacer(minLength: Space.xl)
                
                // Header
                header
                
                // Input bar for free-form questions
                inputBar
                
                // Quick actions grid
                quickActionsGrid
                
                Spacer(minLength: Space.xxl)
            }
            .frame(maxWidth: .infinity)
            .padding(InsetsToken.screen)
        }
        .background(Color.bg)
        .navigationTitle("")
        .navigationBarTitleDisplayMode(.inline)
        .navigationDestination(isPresented: $navigateToCanvas) {
            canvasDestination
        }
        .onAppear {
            preWarmSession()
        }
    }
    
    // MARK: - Header
    
    private var header: some View {
        VStack(alignment: .center, spacing: Space.sm) {
            PovverText("What's on the agenda today?", style: .display, align: .center)
        }
    }
    
    // MARK: - Input Bar
    
    private var inputBar: some View {
        AgentPromptBar(text: $query, placeholder: "Ask anything") {
            entryContext = "freeform:" + query
            navigateToCanvas = true
        }
        .frame(maxWidth: 680)
    }
    
    // MARK: - Quick Actions Grid
    
    private var quickActionsGrid: some View {
        VStack(alignment: .leading, spacing: Space.md) {
            PovverText("Quick actions", style: .subheadline, color: Color.textSecondary)
                .frame(maxWidth: .infinity, alignment: .leading)
            
            let columns = [
                GridItem(.flexible(), spacing: Space.md),
                GridItem(.flexible(), spacing: Space.md)
            ]
            
            LazyVGrid(columns: columns, alignment: .center, spacing: Space.md) {
                // Plan program
                QuickActionCard(title: "Plan program", icon: "calendar.badge.plus") {
                    entryContext = "quick:Plan program"
                    navigateToCanvas = true
                }

                // Analyze progress
                QuickActionCard(title: "Analyze progress", icon: "chart.bar") {
                    entryContext = "quick:Analyze progress"
                    navigateToCanvas = true
                }

                // Create routine
                QuickActionCard(title: "Create routine", icon: "figure.strengthtraining.traditional") {
                    entryContext = "quick:Create routine"
                    navigateToCanvas = true
                }

                // Review plan
                QuickActionCard(title: "Review plan", icon: "doc.text.magnifyingglass") {
                    entryContext = "quick:Review plan"
                    navigateToCanvas = true
                }
            }
        }
        .frame(maxWidth: 820)
    }
    
    // MARK: - Canvas Destination
    
    @ViewBuilder
    private var canvasDestination: some View {
        if let uid = AuthService.shared.currentUser?.uid {
            CanvasScreen(
                userId: uid,
                canvasId: nil,
                purpose: "ad_hoc",
                entryContext: entryContext
            )
        } else {
            EmptyState(title: "Not signed in", message: "Login to view canvas.")
        }
    }
    
    // MARK: - Helpers
    
    private func preWarmSession() {
        guard let uid = AuthService.shared.currentUser?.uid else { return }
        Task { @MainActor in
            SessionPreWarmer.shared.preWarmIfNeeded(
                userId: uid,
                purpose: "ad_hoc",
                trigger: "coach_appear"
            )
        }
    }
    
}

#if DEBUG
struct CoachTabView_Previews: PreviewProvider {
    static var previews: some View {
        NavigationStack {
            CoachTabView(switchToTab: { _ in })
        }
    }
}
#endif
