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
        ScrollView {
            VStack(spacing: Space.xl) {
                Spacer(minLength: Space.xxl)
                
                // Title
                Text("Login")
                    .textStyle(.appTitle)
                    .foregroundColor(.textPrimary)
                
                // Form fields
                VStack(spacing: Space.md) {
                    // Email field
                    authTextField(
                        placeholder: "Email",
                        text: $email,
                        keyboardType: .emailAddress,
                        isSecure: false
                    )
                    
                    // Password field
                    authTextField(
                        placeholder: "Password",
                        text: $password,
                        keyboardType: .default,
                        isSecure: true
                    )
                }
                
                // Error message
                if let errorMessage = errorMessage {
                    Text(errorMessage)
                        .textStyle(.caption)
                        .foregroundColor(.destructive)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal, Space.lg)
                }
                
                // Login button
                PovverButton("Login", style: .primary) {
                    performLogin()
                }
                .disabled(isLoading || email.isEmpty || password.isEmpty)
                
                // Divider
                HStack(spacing: Space.md) {
                    Rectangle()
                        .fill(Color.separator)
                        .frame(height: StrokeWidthToken.hairline)
                    Text("or")
                        .textStyle(.secondary)
                        .foregroundColor(.textTertiary)
                    Rectangle()
                        .fill(Color.separator)
                        .frame(height: StrokeWidthToken.hairline)
                }
                .padding(.vertical, Space.sm)
                
                // Social login buttons
                VStack(spacing: Space.md) {
                    PovverButton("Sign in with Google", style: .secondary, leadingIcon: Image(systemName: "globe")) {
                        // TODO: Implement Google sign-in
                    }
                    
                    PovverButton("Sign in with Apple", style: .secondary, leadingIcon: Image(systemName: "apple.logo")) {
                        // TODO: Implement Apple sign-in
                    }
                }
                
                Spacer(minLength: Space.lg)
                
                // Register link
                Button {
                    onRegister?()
                } label: {
                    Text("Don't have an account? ")
                        .foregroundColor(.textSecondary) +
                    Text("Register")
                        .foregroundColor(.accent)
                        .fontWeight(.semibold)
                }
                .textStyle(.secondary)
                
                Spacer(minLength: Space.xl)
            }
            .padding(.horizontal, Space.lg)
        }
        .background(Color.bg.ignoresSafeArea())
    }
    
    // MARK: - Auth Text Field
    
    @ViewBuilder
    private func authTextField(
        placeholder: String,
        text: Binding<String>,
        keyboardType: UIKeyboardType,
        isSecure: Bool
    ) -> some View {
        Group {
            if isSecure {
                SecureField(placeholder, text: text)
            } else {
                TextField(placeholder, text: text)
                    .keyboardType(keyboardType)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
            }
        }
        .textStyle(.body)
        .foregroundColor(.textPrimary)
        .padding(.horizontal, Space.lg)
        .padding(.vertical, Space.md)
        .background(Color.surface)
        .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.radiusControl))
        .overlay(
            RoundedRectangle(cornerRadius: CornerRadiusToken.radiusControl)
                .strokeBorder(Color.separator, lineWidth: StrokeWidthToken.hairline)
        )
    }
    
    // MARK: - Actions
    
    private func performLogin() {
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
}

struct LoginView_Previews: PreviewProvider {
    static var previews: some View {
        LoginView()
    }
}
