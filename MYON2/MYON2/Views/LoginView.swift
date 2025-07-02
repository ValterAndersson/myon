import SwiftUI
import FirebaseAuth

struct LoginView: View {
    @StateObject private var authService = AuthService.shared
    @ObservedObject private var session = SessionManager.shared
    @State private var email = ""
    @State private var password = ""
    @State private var errorMessage: String?
    @State private var isLoading = false
    @FocusState private var focusedField: LoginField?
    
    var onLogin: ((String) -> Void)? = nil
    var onRegister: (() -> Void)? = nil
    
    enum LoginField {
        case email, password
    }
    
    var body: some View {
        GeometryReader { geometry in
            ScrollView {
                VStack(spacing: 0) {
                    // Header Section
                    AuthHeaderView(
                        title: "Welcome Back",
                        subtitle: "Sign in to continue",
                        geometry: geometry
                    )
                    
                    // Form Section
                    CardContainer(
                        cornerRadius: AuthDesignConstants.cardCornerRadius,
                        shadowRadius: AuthDesignConstants.cardShadowRadius
                    ) {
                        VStack(spacing: AuthDesignConstants.sectionSpacing) {
                            // Email Field
                            NativeTextField(
                                title: "Email Address",
                                text: $email,
                                isSecure: false,
                                keyboardType: .emailAddress,
                                isFocused: focusedField == .email
                            ) {
                                focusedField = .password
                            }
                            .focused($focusedField, equals: .email)
                            .textContentType(.emailAddress)
                            .autocapitalization(.none)
                            .autocorrectionDisabled()
                            
                            // Password Field
                            NativeTextField(
                                title: "Password",
                                text: $password,
                                isSecure: true,
                                keyboardType: .default,
                                isFocused: focusedField == .password
                            ) {
                                if isFormValid {
                                    handleLogin()
                                }
                            }
                            .focused($focusedField, equals: .password)
                            .textContentType(.password)
                            
                            // Error Message
                            if let errorMessage = errorMessage {
                                AuthErrorMessage(message: errorMessage)
                            }
                            
                            // Login Button
                            Button(action: handleLogin) {
                                HStack {
                                    if isLoading {
                                        ProgressView()
                                            .progressViewStyle(CircularProgressViewStyle(tint: .white))
                                            .scaleEffect(0.8)
                                    } else {
                                        Text("Sign In")
                                            .font(.system(size: 16, weight: .semibold))
                                    }
                                }
                                .frame(height: AuthDesignConstants.buttonHeight)
                            }
                            .buttonStyle(PrimaryActionButtonStyle())
                            .disabled(isLoading || !isFormValid)
                            .animation(.easeInOut(duration: AuthDesignConstants.animationDuration), value: isLoading)
                        }
                        .padding(.vertical, 8)
                    }
                    .padding(.horizontal, AuthDesignConstants.defaultPadding)
                    .padding(.top, 20)
                    
                    // Divider
                    AuthDivider()
                    
                    // Social Sign In Buttons
                    VStack(spacing: 12) {
                        SocialSignInButton(
                            title: "Continue with Apple",
                            icon: "apple.logo",
                            backgroundColor: .black,
                            foregroundColor: .white
                        ) {
                            HapticFeedbackManager.shared.light()
                            // TODO: Implement Apple sign-in
                        }
                        
                        SocialSignInButton(
                            title: "Continue with Google",
                            icon: "globe",
                            backgroundColor: .white,
                            foregroundColor: .black
                        ) {
                            HapticFeedbackManager.shared.light()
                            // TODO: Implement Google sign-in
                        }
                    }
                    .padding(.horizontal, AuthDesignConstants.defaultPadding)
                    
                    // Register Link
                    HStack {
                        Text("Don't have an account?")
                            .font(.system(size: 15))
                            .foregroundColor(.secondary)
                        
                        Button("Sign Up") {
                            HapticFeedbackManager.shared.light()
                            onRegister?()
                        }
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundColor(.blue)
                    }
                    .padding(.top, 32)
                    .padding(.bottom, max(40, geometry.safeAreaInsets.bottom + 20))
                }
            }
        }
        .background(Color(.systemGroupedBackground))
        .onTapGesture {
            focusedField = nil
        }
        .onAppear {
            DispatchQueue.main.asyncAfter(deadline: .now() + AuthDesignConstants.focusDelay) {
                focusedField = .email
            }
        }
    }
    
    private var isFormValid: Bool {
        return email.isValidEmail && !password.isEmpty
    }
    
    private func handleLogin() {
        HapticFeedbackManager.shared.light()
        focusedField = nil
        isLoading = true
        
        Task {
            do {
                try await authService.signIn(email: email, password: password)
                if let user = Auth.auth().currentUser {
                    await MainActor.run {
                        HapticFeedbackManager.shared.success()
                        session.startSession(userId: user.uid)
                        onLogin?(user.uid)
                        errorMessage = nil
                    }
                }
            } catch {
                await MainActor.run {
                    HapticFeedbackManager.shared.error()
                    errorMessage = error.localizedDescription
                }
            }
            await MainActor.run {
                isLoading = false
            }
        }
    }
}

struct LoginView_Previews: PreviewProvider {
    static var previews: some View {
        LoginView()
    }
} 