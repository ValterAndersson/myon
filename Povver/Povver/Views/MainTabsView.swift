import SwiftUI

/// Main navigation tabs for the app
/// Updated from 2-tab (Home/Workout) to 5-tab (Coach/Train/Library/History/Profile) structure
enum MainTab: String, CaseIterable {
    case coach
    case train
    case library
    case history
    case profile
    
    /// SF Symbol icon name (outline style)
    var iconName: String {
        switch self {
        case .coach: return "bubble.left.and.bubble.right"
        case .train: return "figure.strengthtraining.traditional"
        case .library: return "rectangle.stack"
        case .history: return "clock.arrow.circlepath"
        case .profile: return "person.crop.circle"
        }
    }
    
    /// Tab label (single word)
    var label: String {
        switch self {
        case .coach: return "Coach"
        case .train: return "Train"
        case .library: return "Library"
        case .history: return "History"
        case .profile: return "Profile"
        }
    }
    
    /// Migration from old MainTab enum values
    static func migrate(from rawValue: String) -> MainTab {
        switch rawValue {
        case "home": return .coach  // Old "home" maps to new "coach"
        case "workout": return .train  // Old "workout" maps to new "train"
        default:
            // Try direct match first
            if let tab = MainTab(rawValue: rawValue) {
                return tab
            }
            return .coach  // Default fallback
        }
    }
}

struct MainTabsView: View {
    /// Persisted tab selection with migration support
    @AppStorage("selectedTab") private var selectedTabRaw: String = MainTab.coach.rawValue
    
    /// Computed binding that handles migration from old values
    private var selectedTab: Binding<MainTab> {
        Binding(
            get: { MainTab.migrate(from: selectedTabRaw) },
            set: { selectedTabRaw = $0.rawValue }
        )
    }

    var body: some View {
        TabView(selection: selectedTab) {
            // Coach Tab (formerly Home)
            NavigationStack {
                CoachTabView(switchToTab: switchToTab)
            }
            .tabItem { Label(MainTab.coach.label, systemImage: MainTab.coach.iconName) }
            .tag(MainTab.coach)

            // Train Tab (formerly Start Workout)
            NavigationStack {
                TrainTabView()
            }
            .tabItem { Label(MainTab.train.label, systemImage: MainTab.train.iconName) }
            .tag(MainTab.train)

            // Library Tab (new)
            NavigationStack {
                LibraryView()
            }
            .tabItem { Label(MainTab.library.label, systemImage: MainTab.library.iconName) }
            .tag(MainTab.library)

            // History Tab (new)
            NavigationStack {
                HistoryView()
            }
            .tabItem { Label(MainTab.history.label, systemImage: MainTab.history.iconName) }
            .tag(MainTab.history)

            // Profile Tab (new)
            NavigationStack {
                ProfileView()
            }
            .tabItem { Label(MainTab.profile.label, systemImage: MainTab.profile.iconName) }
            .tag(MainTab.profile)
        }
        .tint(Color.accent)
    }
    
    /// Switch to a specific tab programmatically
    /// Used by Coach tab to navigate to Train tab
    private func switchToTab(_ tab: MainTab) {
        selectedTabRaw = tab.rawValue
    }
}

#if DEBUG
struct MainTabsView_Previews: PreviewProvider {
    static var previews: some View { MainTabsView() }
}
#endif
