import SwiftUI

enum MainTab {
    case chat, components, canvas
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

            // Components Gallery
            NavigationStack {
                ComponentGallery()
            }
            .tabItem { Label("Components", systemImage: "rectangle.3.offgrid") }
            .tag(MainTab.components)

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
        }
    }
}

#if DEBUG
struct MainTabsView_Previews: PreviewProvider {
    static var previews: some View { MainTabsView() }
}
#endif


