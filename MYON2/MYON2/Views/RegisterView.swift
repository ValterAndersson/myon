import SwiftUI
import FirebaseAuth

struct RegisterView: View {
    @StateObject private var authService = AuthService.shared
    @ObservedObject private var session = SessionManager.shared
    @State private var email = ""
    @State private var password = ""
    @State private var confirmPassword = ""
    @State private var errorMessage: String?
    @State private var isLoading = false
    @FocusState private var focusedField: RegisterField?
    
    var onRegister: ((String) -> Void)? = nil
    var onBackToLogin: (() -> Void)? = nil
    
    enum RegisterField {
        case email, password, confirmPassword
    }
    
    var body: some View {
        GeometryReader { geometry in
            ScrollView {
                VStack(spacing: 0) {
                    // Header Section
                    AuthHeaderView(
                        title: "Create Account",
                        subtitle: "Sign up to get started",
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
                                focusedField = .confirmPassword
                            }
                            .focused($focusedField, equals: .password)
                            .textContentType(.newPassword)
                            
                            // Confirm Password Field
                            NativeTextField(
                                title: "Confirm Password",
                                text: $confirmPassword,
                                isSecure: true,
                                keyboardType: .default,
                                isFocused: focusedField == .confirmPassword
                            ) {
                                if isFormValid {
                                    handleRegister()
                                }
                            }
                            .focused($focusedField, equals: .confirmPassword)
                            .textContentType(.newPassword)
                            
                            // Password Validation
                            if !password.isEmpty {
                                VStack(spacing: 8) {
                                    ForEach(PasswordValidator.requirements(for: password), id: \.text) { requirement in
                                        PasswordRequirement(
                                            text: requirement.text,
                                            isValid: requirement.isValid
                                        )
                                    }
                                }
                                .transition(.opacity.combined(with: .scale(scale: 0.8)))
                                .animation(.spring(
                                    response: AuthDesignConstants.springAnimationResponse,
                                    dampingFraction: AuthDesignConstants.springAnimationDamping
                                ), value: password)
                            }
                            
                            // Password Match Validation
                            if !confirmPassword.isEmpty && password != confirmPassword {
                                HStack {
                                    Image(systemName: "xmark.circle.fill")
                                        .foregroundColor(.red)
                                    Text("Passwords don't match")
                                        .font(.system(size: 14, weight: .medium))
                                        .foregroundColor(.red)
                                    Spacer()
                                }
                                .padding(.horizontal, 4)
                                .transition(.opacity.combined(with: .scale(scale: 0.8)))
                                .animation(.spring(
                                    response: AuthDesignConstants.springAnimationResponse,
                                    dampingFraction: AuthDesignConstants.springAnimationDamping
                                ), value: confirmPassword)
                            }
                            
                            // Error Message
                            if let errorMessage = errorMessage {
                                AuthErrorMessage(message: errorMessage)
                            }
                            
                            // Register Button
                            Button(action: handleRegister) {
                                HStack {
                                    if isLoading {
                                        ProgressView()
                                            .progressViewStyle(CircularProgressViewStyle(tint: .white))
                                            .scaleEffect(0.8)
                                    } else {
                                        Text("Create Account")
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
                    
                    // Social Sign Up Buttons
                    VStack(spacing: 12) {
                        SocialSignInButton(
                            title: "Sign up with Apple",
                            icon: "apple.logo",
                            backgroundColor: .black,
                            foregroundColor: .white
                        ) {
                            HapticFeedbackManager.shared.light()
                            // TODO: Implement Apple sign-in
                        }
                        
                        SocialSignInButton(
                            title: "Sign up with Google",
                            icon: "globe",
                            backgroundColor: .white,
                            foregroundColor: .black
                        ) {
                            HapticFeedbackManager.shared.light()
                            // TODO: Implement Google sign-in
                        }
                    }
                    .padding(.horizontal, AuthDesignConstants.defaultPadding)
                    
                    // Login Link
                    HStack {
                        Text("Already have an account?")
                            .font(.system(size: 15))
                            .foregroundColor(.secondary)
                        
                        Button("Sign In") {
                            HapticFeedbackManager.shared.light()
                            onBackToLogin?()
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
        return email.isValidEmail 
            && password.passwordStrength != .weak
            && password == confirmPassword
    }
    
    private func handleRegister() {
        HapticFeedbackManager.shared.light()
        focusedField = nil
        isLoading = true
        
        Task {
            do {
                try await authService.signUp(email: email, password: password)
                if let user = Auth.auth().currentUser {
                    await MainActor.run {
                        HapticFeedbackManager.shared.success()
                        session.startSession(userId: user.uid)
                        onRegister?(user.uid)
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

struct RegisterView_Previews: PreviewProvider {
    static var previews: some View {
        RegisterView()
    }
} 