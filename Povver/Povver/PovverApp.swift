import SwiftUI
import GoogleSignIn

@main
struct PovverApp: App {
    init() {
        FirebaseConfig.shared.configure()
    }

    var body: some Scene {
        WindowGroup {
            RootView()
                .onOpenURL { url in
                    GIDSignIn.sharedInstance.handle(url)
                }
        }
    }
}
