import SwiftUI
import FirebaseAuth

struct RegisterView: View {
    @ObservedObject private var authService = AuthService.shared
    @ObservedObject private var session = SessionManager.shared
    @State private var email = ""
    @State private var password = ""
    @State private var errorMessage: String?
    @State private var isLoading = false
    @State private var showingNewAccountConfirmation = false
    @State private var pendingSSOResult: AuthService.SSOSignInResult?
    var onRegister: ((String) -> Void)? = nil
    var onBackToLogin: (() -> Void)? = nil

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

                        Text("Create your account")
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

                    // Error message
                    if let errorMessage = errorMessage {
                        Text(errorMessage)
                            .textStyle(.caption)
                            .foregroundColor(.destructive)
                            .multilineTextAlignment(.center)
                            .padding(.horizontal, Space.lg)
                    }

                    // Register button
                    PovverButton("Create Account", style: .primary) {
                        performRegistration()
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

                    // Social signup buttons
                    VStack(spacing: Space.md) {
                        PovverButton("Sign up with Google", style: .secondary, leadingIcon: Image(systemName: "globe")) {
                            performGoogleSignIn()
                        }
                        .disabled(isLoading)

                        PovverButton("Sign up with Apple", style: .secondary, leadingIcon: Image(systemName: "apple.logo")) {
                            performAppleSignIn()
                        }
                        .disabled(isLoading)
                    }

                    Spacer(minLength: Space.xxxl)

                    // Login link
                    Button {
                        onBackToLogin?()
                    } label: {
                        Text("Already have an account? ")
                            .foregroundColor(.textSecondary) +
                        Text("Login")
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
        .confirmationDialog(
            "Create Account",
            isPresented: $showingNewAccountConfirmation
        ) {
            Button("Create Account") {
                confirmSSOAccount()
            }
            Button("Cancel", role: .cancel) {
                try? authService.signOut()
            }
        } message: {
            if case .newUser(_, let email, _) = pendingSSOResult {
                Text("Create a new Povver account with \(email)?")
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
                        onRegister?(user.uid)
                    }
                case .newUser:
                    pendingSSOResult = result
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
                    provider: ssoProvider ?? .apple
                )
                session.startSession(userId: userId)
                onRegister?(userId)
            } catch {
                errorMessage = AuthService.friendlyAuthError(error)
            }
            isLoading = false
        }
    }

    private func performRegistration() {
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
                errorMessage = AuthService.friendlyAuthError(error)
            }
            isLoading = false
        }
    }
}

struct RegisterView_Previews: PreviewProvider {
    static var previews: some View {
        RegisterView()
    }
}
