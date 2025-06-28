import SwiftUI
import FirebaseFirestore

enum AppFlow {
    case login
    case register
    case onboarding(String)
    case home
}

struct RootView: View {
    @StateObject private var session = SessionManager.shared
    @State private var flow: AppFlow = .login
    @State private var isCheckingOnboarding = false

    
    var body: some View {
        NavigationStack {
            switch flow {
            case .login:
                LoginView(onLogin: { userId in
                    checkOnboarding(userId: userId)
                }, onRegister: {
                    flow = .register
                })
            case .register:
                RegisterView(onRegister: { userId in
                    checkOnboarding(userId: userId)
                }, onBackToLogin: {
                    flow = .login
                })
            case .onboarding(let userId):
                OnboardingView(userId: userId, onComplete: {
                    flow = .home
                })
            case .home:
                HomePageView(onLogout: {
                    flow = .login
                })
            }
            if isCheckingOnboarding {
                ProgressView("Checking onboarding status...")
            }
        }
    }
    
    private func checkOnboarding(userId: String) {
        isCheckingOnboarding = true
        Task {
            do {
                let userAttributes = try await UserRepository().getUserAttributes(userId: userId)
                print("Debug - UserAttributes: \(String(describing: userAttributes))")
                
                // If no attributes exist or required fields are missing, show onboarding
                let needsOnboarding = userAttributes == nil || 
                                    userAttributes?.fitnessGoal == nil || 
                                    userAttributes?.fitnessLevel == nil || 
                                    userAttributes?.equipment == nil
                
                print("Debug - Needs onboarding: \(needsOnboarding)")
                
                if needsOnboarding {
                    print("Debug - Showing onboarding")
                    flow = .onboarding(userId)
                } else {
                    print("Debug - Proceeding to home")
                    flow = .home
                }
            } catch {
                print("Error checking onboarding status: \(error)")
                flow = .home
            }
            isCheckingOnboarding = false
        }
    }

}

struct RootView_Previews: PreviewProvider {
    static var previews: some View {
        RootView()
    }
} 