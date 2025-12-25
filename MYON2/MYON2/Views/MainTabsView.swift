import SwiftUI

enum MainTab {
    case chat, routines, templates, canvas, components
}

struct MainTabsView: View {
    @State private var selected: MainTab = .chat

    var body: some View {
        TabView(selection: $selected) {
            // Chat Home
            NavigationStack {
                ChatHomeEntry()
            }
            .tabItem { Label("Chat", systemImage: "message") }
            .tag(MainTab.chat)

            // Routines
            RoutinesListView()
                .tabItem { Label("Routines", systemImage: "figure.run") }
                .tag(MainTab.routines)

            // Templates
            TemplatesListView()
                .tabItem { Label("Templates", systemImage: "doc.text") }
                .tag(MainTab.templates)

            // Canvas
            Group {
                if let uid = AuthService.shared.currentUser?.uid {
                    NavigationStack { CanvasScreen(userId: uid, canvasId: nil, purpose: "ad_hoc", entryContext: nil) }
                } else {
                    NavigationStack { EmptyState(title: "Not signed in", message: "Login to view canvas.") }
                }
            }
            .tabItem { Label("Canvas", systemImage: "square.grid.2x2") }
            .tag(MainTab.canvas)

            // Components Gallery (Development only)
            #if DEBUG
            NavigationStack {
                ComponentGallery()
            }
            .tabItem { Label("Dev", systemImage: "rectangle.3.offgrid") }
            .tag(MainTab.components)
            #endif
        }
    }
}

#if DEBUG
struct MainTabsView_Previews: PreviewProvider {
    static var previews: some View { MainTabsView() }
}
#endif
