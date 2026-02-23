import SwiftUI
import FirebaseAuth

struct LoginView: View {
    @ObservedObject private var authService = AuthService.shared
    @ObservedObject private var session = SessionManager.shared
    @State private var email = ""
    @State private var password = ""
    @State private var errorMessage: String?
    @State private var isLoading = false
    @State private var showingForgotPassword = false
    @State private var showingNewAccountConfirmation = false
    @State private var pendingSSOResult: AuthService.SSOSignInResult?
    var onLogin: ((String) -> Void)? = nil
    var onRegister: (() -> Void)? = nil

    var body: some View {
        GeometryReader { geometry in
            ScrollView {
                VStack(spacing: Space.xl) {
                    Spacer(minLength: Space.xxxl)

                    // Brand header
                    VStack(spacing: Space.sm) {
                        Text("POVVER")
                            .font(.system(size: 40, weight: .black, design: .default))
                            .tracking(2)
                            .foregroundColor(.textPrimary)

                        Text("Welcome back")
                            .textStyle(.secondary)
                            .foregroundColor(.textSecondary)
                    }

                    // Form fields
                    VStack(spacing: Space.md) {
                        authTextField(
                            placeholder: "Email",
                            text: $email,
                            keyboardType: .emailAddress,
                            isSecure: false
                        )

                        authTextField(
                            placeholder: "Password",
                            text: $password,
                            keyboardType: .default,
                            isSecure: true
                        )
                    }

                    // Forgot password
                    HStack {
                        Spacer()
                        Button {
                            showingForgotPassword = true
                        } label: {
                            Text("Forgot Password?")
                                .textStyle(.caption)
                                .foregroundColor(.accent)
                        }
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
                            .fill(Color.separatorLine)
                            .frame(height: StrokeWidthToken.hairline)
                        Text("or")
                            .textStyle(.secondary)
                            .foregroundColor(.textTertiary)
                        Rectangle()
                            .fill(Color.separatorLine)
                            .frame(height: StrokeWidthToken.hairline)
                    }
                    .padding(.vertical, Space.sm)

                    // Social login buttons
                    VStack(spacing: Space.md) {
                        PovverButton("Sign in with Google", style: .secondary, leadingIcon: Image(systemName: "globe")) {
                            performGoogleSignIn()
                        }
                        .disabled(isLoading)

                        PovverButton("Sign in with Apple", style: .secondary, leadingIcon: Image(systemName: "apple.logo")) {
                            performAppleSignIn()
                        }
                        .disabled(isLoading)
                    }

                    Spacer(minLength: Space.xxxl)

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
                }
                .padding(.horizontal, Space.lg)
                .padding(.vertical, Space.lg)
                .frame(minHeight: geometry.size.height)
            }
        }
        .background(Color.bg.ignoresSafeArea())
        .sheet(isPresented: $showingForgotPassword) {
            ForgotPasswordView(prefillEmail: email)
        }
        .confirmationDialog(
            "Create Account",
            isPresented: $showingNewAccountConfirmation
        ) {
            Button("Create Account") {
                confirmSSOAccount()
            }
            Button("Cancel", role: .cancel) {
                // User declined — sign out the Firebase auth session that was created
                AnalyticsService.shared.ssoConfirmationCancelled(provider: ssoProvider == .apple ? .apple : .google)
                try? authService.signOut()
            }
        } message: {
            if case .newUser(_, let email, _) = pendingSSOResult {
                Text("No account found for \(email). Would you like to create one?")
            }
        }
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
                .strokeBorder(Color.separatorLine, lineWidth: StrokeWidthToken.hairline)
        )
    }

    // MARK: - Actions

    @State private var ssoProvider: AuthProvider?

    private func performGoogleSignIn() {
        ssoProvider = .google
        performSSOSignIn { try await authService.signInWithGoogle() }
    }

    private func performAppleSignIn() {
        ssoProvider = .apple
        performSSOSignIn { try await authService.signInWithApple() }
    }

    private func performSSOSignIn(_ signIn: @escaping () async throws -> AuthService.SSOSignInResult) {
        isLoading = true
        Task {
            do {
                let result = try await signIn()
                switch result {
                case .existingUser:
                    if let user = Auth.auth().currentUser {
                        session.startSession(userId: user.uid)
                        AnalyticsService.shared.loginCompleted(provider: ssoProvider == .apple ? .apple : .google)
                        onLogin?(user.uid)
                    }
                case .newUser:
                    pendingSSOResult = result
                    AnalyticsService.shared.ssoConfirmationShown(provider: ssoProvider == .apple ? .apple : .google)
                    showingNewAccountConfirmation = true
                }
                errorMessage = nil
            } catch {
                errorMessage = AuthService.friendlyAuthError(error)
            }
            isLoading = false
        }
    }

    private func confirmSSOAccount() {
        guard case .newUser(let userId, let email, let name) = pendingSSOResult else { return }
        isLoading = true
        Task {
            do {
                try await authService.confirmSSOAccountCreation(
                    userId: userId,
                    email: email,
                    name: name,
                    provider: ssoProvider ?? .google
                )
                session.startSession(userId: userId)
                onLogin?(userId)
            } catch {
                errorMessage = AuthService.friendlyAuthError(error)
            }
            isLoading = false
        }
    }

    private func performLogin() {
        isLoading = true
        Task {
            do {
                try await authService.signIn(email: email, password: password)
                if let user = Auth.auth().currentUser {
                    session.startSession(userId: user.uid)
                    AnalyticsService.shared.loginCompleted(provider: .email)
                    onLogin?(user.uid)
                }
                errorMessage = nil
            } catch {
                errorMessage = AuthService.friendlyAuthError(error)
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
