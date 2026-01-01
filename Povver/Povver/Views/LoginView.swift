import SwiftUI
import FirebaseAuth

struct LoginView: View {
    @StateObject private var authService = AuthService.shared
    @ObservedObject private var session = SessionManager.shared
    @State private var email = ""
    @State private var password = ""
    @State private var errorMessage: String?
    @State private var isLoading = false
    var onLogin: ((String) -> Void)? = nil
    var onRegister: (() -> Void)? = nil
    
    var body: some View {
        VStack(spacing: 24) {
            Text("Login").font(.largeTitle).bold()
            TextField("Email", text: $email)
                .autocapitalization(.none)
                .textFieldStyle(RoundedBorderTextFieldStyle())
            SecureField("Password", text: $password)
                .textFieldStyle(RoundedBorderTextFieldStyle())
            if let errorMessage = errorMessage {
                Text(errorMessage).foregroundColor(.red)
            }
            Button("Login") {
                isLoading = true
                Task {
                    do {
                        try await authService.signIn(email: email, password: password)
                        if let user = Auth.auth().currentUser {
                            session.startSession(userId: user.uid)
                            onLogin?(user.uid)
                        }
                        errorMessage = nil
                    } catch {
                        errorMessage = error.localizedDescription
                    }
                    isLoading = false
                }
            }
            .disabled(isLoading)
            Divider()
            Button("Sign in with Google") {
                // TODO: Implement Google sign-in
            }
            Button("Sign in with Apple") {
                // TODO: Implement Apple sign-in
            }
            Button("Don't have an account? Register") {
                onRegister?()
            }
        }
        .padding()
    }
}

struct LoginView_Previews: PreviewProvider {
    static var previews: some View {
        LoginView()
    }
} 