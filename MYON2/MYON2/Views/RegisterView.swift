import SwiftUI
import FirebaseAuth

struct RegisterView: View {
    @StateObject private var authService = AuthService.shared
    @ObservedObject private var session = SessionManager.shared
    @State private var email = ""
    @State private var password = ""
    @State private var errorMessage: String?
    @State private var isLoading = false
    var onRegister: ((String) -> Void)? = nil
    var onBackToLogin: (() -> Void)? = nil
    var body: some View {
        VStack(spacing: 24) {
            Text("Register").font(.largeTitle).bold()
            TextField("Email", text: $email)
                .autocapitalization(.none)
                .textFieldStyle(RoundedBorderTextFieldStyle())
            SecureField("Password", text: $password)
                .textFieldStyle(RoundedBorderTextFieldStyle())
            if let errorMessage = errorMessage {
                Text(errorMessage).foregroundColor(.red)
            }
            Button("Register") {
                isLoading = true
                Task {
                    do {
                        try await authService.signUp(email: email, password: password)
                        if let user = Auth.auth().currentUser {
                            session.startSession(userId: user.uid)
                            onRegister?(user.uid)
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
            Button("Sign up with Google") {
                // TODO: Implement Google sign-in
            }
            Button("Sign up with Apple") {
                // TODO: Implement Apple sign-in
            }
            Button("Already have an account? Log In") {
                onBackToLogin?()
            }
        }
        .padding()
    }
}

struct RegisterView_Previews: PreviewProvider {
    static var previews: some View {
        RegisterView()
    }
} 