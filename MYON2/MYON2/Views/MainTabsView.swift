import SwiftUI

enum MainTab {
    case home, workout
    #if DEBUG
    case components
    #endif
}

struct MainTabsView: View {
    @State private var selected: MainTab = .home

    var body: some View {
        TabView(selection: $selected) {
            // Home (Chat)
            NavigationStack {
                ChatHomeEntry()
            }
            .tabItem { Label("Home", systemImage: "house") }
            .tag(MainTab.home)

            // Start Workout (Focus Mode)
            NavigationStack {
                FocusModeWorkoutScreen()
            }
            .tabItem { Label("Start Workout", systemImage: "figure.strengthtraining.traditional") }
            .tag(MainTab.workout)

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
