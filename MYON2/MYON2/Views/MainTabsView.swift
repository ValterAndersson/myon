import SwiftUI

enum MainTab {
    case home, workout
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
        }
    }
}

#if DEBUG
struct MainTabsView_Previews: PreviewProvider {
    static var previews: some View { MainTabsView() }
}
#endif
