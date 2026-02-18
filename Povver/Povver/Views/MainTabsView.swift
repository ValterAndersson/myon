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

    @StateObject private var recommendationsVM = RecommendationsViewModel()
    @StateObject private var workoutService = FocusModeWorkoutService.shared
    @State private var showRecommendations = false
    @State private var bannerElapsedTime: TimeInterval = 0
    @State private var bannerTimer: Timer? = nil

    /// Whether the floating workout banner should be visible
    private var showWorkoutBanner: Bool {
        workoutService.workout != nil && MainTab.migrate(from: selectedTabRaw) != .train
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
        .overlay {
            // GeometryReader to position bell below the safe area (status bar / Dynamic Island)
            if recommendationsVM.pendingCount > 0 {
                GeometryReader { geometry in
                    HStack {
                        Spacer()
                        NotificationBell(badgeCount: recommendationsVM.pendingCount) {
                            showRecommendations = true
                        }
                        .padding(.trailing, Space.lg)
                    }
                    .padding(.top, geometry.safeAreaInsets.top + Space.sm)
                }
            }
        }
        .overlay(alignment: .bottom) {
            if showWorkoutBanner {
                FloatingWorkoutBanner(
                    workoutName: workoutService.workout?.name ?? "Workout",
                    elapsedTime: bannerElapsedTime,
                    onTap: { selectedTabRaw = MainTab.train.rawValue }
                )
                .padding(.horizontal, Space.md)
                .padding(.bottom, 52) // Above tab bar
                .transition(.move(edge: .bottom).combined(with: .opacity))
            }
        }
        .animation(.easeInOut(duration: 0.25), value: showWorkoutBanner)
        .onChange(of: showWorkoutBanner) { _, visible in
            if visible {
                startBannerTimer()
            } else {
                stopBannerTimer()
            }
        }
        .onAppear {
            if showWorkoutBanner {
                startBannerTimer()
            }
        }
        .sheet(isPresented: $showRecommendations) {
            RecommendationsFeedView(viewModel: recommendationsVM)
        }
        .onChange(of: selectedTabRaw) { _, newTab in
            AnalyticsService.shared.tabViewed(newTab)
        }
        .task {
            if let userId = AuthService.shared.currentUser?.uid {
                recommendationsVM.startListening(userId: userId)
            }
        }
    }
    
    /// Switch to a specific tab programmatically
    /// Used by Coach tab to navigate to Train tab
    private func switchToTab(_ tab: MainTab) {
        selectedTabRaw = tab.rawValue
    }

    // MARK: - Banner Timer

    private func startBannerTimer() {
        stopBannerTimer()
        updateBannerElapsed()
        bannerTimer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { _ in
            Task { @MainActor in
                updateBannerElapsed()
            }
        }
    }

    private func stopBannerTimer() {
        bannerTimer?.invalidate()
        bannerTimer = nil
    }

    private func updateBannerElapsed() {
        if let startTime = workoutService.workout?.startTime {
            bannerElapsedTime = Date().timeIntervalSince(startTime)
        }
    }
}

#if DEBUG
struct MainTabsView_Previews: PreviewProvider {
    static var previews: some View { MainTabsView() }
}
#endif
