import SwiftUI
import FirebaseFirestore

enum AppFlow {
    case login
    case register
    case main
}

struct RootView: View {
    @StateObject private var session = SessionManager.shared
    @State private var flow: AppFlow = .login

    
    var body: some View {
        NavigationStack {
            switch flow {
            case .login:
                LoginView(onLogin: { _ in
                    flow = .main
                }, onRegister: {
                    flow = .register
                })
            case .register:
                RegisterView(onRegister: { _ in
                    flow = .main
                }, onBackToLogin: {
                    flow = .login
                })
            case .main:
                MainTabsView()
            }
        }
    }
    
    private func _noop() {}

}

struct RootView_Previews: PreviewProvider {
    static var previews: some View {
        RootView()
    }
} 