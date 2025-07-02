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
                    VStack(spacing: 16) {
                        Spacer()
                            .frame(height: max(60, geometry.safeAreaInsets.top + 20))
                        
                        Text("Create Account")
                            .font(.system(size: 32, weight: .bold, design: .rounded))
                            .foregroundColor(.primary)
                        
                        Text("Sign up to get started")
                            .font(.system(size: 16, weight: .medium))
                            .foregroundColor(.secondary)
                    }
                    .frame(minHeight: 200)
                    
                    // Form Section
                    CardContainer(cornerRadius: 24, shadowRadius: 8) {
                        VStack(spacing: 24) {
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
                                    PasswordRequirement(
                                        text: "At least 8 characters",
                                        isValid: password.count >= 8
                                    )
                                    PasswordRequirement(
                                        text: "Contains uppercase letter",
                                        isValid: password.range(of: "[A-Z]", options: .regularExpression) != nil
                                    )
                                    PasswordRequirement(
                                        text: "Contains number",
                                        isValid: password.range(of: "[0-9]", options: .regularExpression) != nil
                                    )
                                }
                                .transition(.opacity.combined(with: .scale(scale: 0.8)))
                                .animation(.spring(response: 0.5, dampingFraction: 0.8), value: password)
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
                                .animation(.spring(response: 0.5, dampingFraction: 0.8), value: confirmPassword)
                            }
                            
                            // Error Message
                            if let errorMessage = errorMessage {
                                HStack {
                                    Image(systemName: "exclamationmark.triangle.fill")
                                        .foregroundColor(.red)
                                    Text(errorMessage)
                                        .font(.system(size: 14, weight: .medium))
                                        .foregroundColor(.red)
                                    Spacer()
                                }
                                .padding(.horizontal, 4)
                                .transition(.opacity.combined(with: .scale(scale: 0.8)))
                                .animation(.spring(response: 0.5, dampingFraction: 0.8), value: errorMessage)
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
                                .frame(height: 50)
                            }
                            .buttonStyle(PrimaryActionButtonStyle())
                            .disabled(isLoading || !isFormValid)
                            .animation(.easeInOut(duration: 0.2), value: isLoading)
                        }
                        .padding(.vertical, 8)
                    }
                    .padding(.horizontal, 24)
                    .padding(.top, 20)
                    
                    // Divider
                    HStack {
                        Rectangle()
                            .frame(height: 1)
                            .foregroundColor(.gray.opacity(0.3))
                        Text("or")
                            .font(.system(size: 14, weight: .medium))
                            .foregroundColor(.secondary)
                            .padding(.horizontal, 16)
                        Rectangle()
                            .frame(height: 1)
                            .foregroundColor(.gray.opacity(0.3))
                    }
                    .padding(.horizontal, 24)
                    .padding(.vertical, 32)
                    
                    // Social Sign Up Buttons
                    VStack(spacing: 12) {
                        SocialSignInButton(
                            title: "Sign up with Apple",
                            icon: "apple.logo",
                            backgroundColor: .black,
                            foregroundColor: .white
                        ) {
                            // TODO: Implement Apple sign-in
                            lightHapticFeedback()
                        }
                        
                        SocialSignInButton(
                            title: "Sign up with Google",
                            icon: "globe",
                            backgroundColor: .white,
                            foregroundColor: .black
                        ) {
                            // TODO: Implement Google sign-in
                            lightHapticFeedback()
                        }
                    }
                    .padding(.horizontal, 24)
                    
                    // Login Link
                    HStack {
                        Text("Already have an account?")
                            .font(.system(size: 15))
                            .foregroundColor(.secondary)
                        
                        Button("Sign In") {
                            lightHapticFeedback()
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
            // Small delay to feel more natural
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
                focusedField = .email
            }
        }
    }
    
    private var isFormValid: Bool {
        return !email.isEmpty 
            && password.count >= 8
            && password.range(of: "[A-Z]", options: .regularExpression) != nil
            && password.range(of: "[0-9]", options: .regularExpression) != nil
            && password == confirmPassword
    }
    
    private func handleRegister() {
        lightHapticFeedback()
        focusedField = nil
        isLoading = true
        
        Task {
            do {
                try await authService.signUp(email: email, password: password)
                if let user = Auth.auth().currentUser {
                    await MainActor.run {
                        successHapticFeedback()
                        session.startSession(userId: user.uid)
                        onRegister?(user.uid)
                        errorMessage = nil
                    }
                }
            } catch {
                await MainActor.run {
                    errorHapticFeedback()
                    errorMessage = error.localizedDescription
                }
            }
            await MainActor.run {
                isLoading = false
            }
        }
    }
    
    private func lightHapticFeedback() {
        let impactFeedback = UIImpactFeedbackGenerator(style: .light)
        impactFeedback.impactOccurred()
    }
    
    private func successHapticFeedback() {
        let notificationFeedback = UINotificationFeedbackGenerator()
        notificationFeedback.notificationOccurred(.success)
    }
    
    private func errorHapticFeedback() {
        let notificationFeedback = UINotificationFeedbackGenerator()
        notificationFeedback.notificationOccurred(.error)
    }
}

struct PasswordRequirement: View {
    let text: String
    let isValid: Bool
    
    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: isValid ? "checkmark.circle.fill" : "circle")
                .foregroundColor(isValid ? .green : .secondary)
                .font(.system(size: 14))
            
            Text(text)
                .font(.system(size: 14, weight: .medium))
                .foregroundColor(isValid ? .green : .secondary)
            
            Spacer()
        }
        .animation(.easeInOut(duration: 0.2), value: isValid)
    }
}

struct RegisterView_Previews: PreviewProvider {
    static var previews: some View {
        RegisterView()
    }
} 