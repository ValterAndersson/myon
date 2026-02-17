import SwiftUI
import GoogleSignIn

@main
struct PovverApp: App {
    init() {
        FirebaseConfig.shared.configure()
        AnalyticsService.shared.appOpened()

        // Initialize SubscriptionService to start transaction listener
        _ = SubscriptionService.shared
    }

    var body: some Scene {
        WindowGroup {
            RootView()
                .onOpenURL { url in
                    GIDSignIn.sharedInstance.handle(url)
                }
                .task {
                    // Check subscription status on app launch
                    await SubscriptionService.shared.checkEntitlements()
                }
        }
    }
}
