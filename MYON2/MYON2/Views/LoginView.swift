import SwiftUI
import FirebaseAuth

struct LoginView: View {
    @StateObject private var authService = AuthService.shared
    @ObservedObject private var session = SessionManager.shared
    @State private var email = ""
    @State private var password = ""
    @State private var errorMessage: String?
    @State private var isLoading = false
    @State private var emailFocused = false
    @State private var passwordFocused = false
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
                    VStack(spacing: 16) {
                        Spacer()
                            .frame(height: max(60, geometry.safeAreaInsets.top + 20))
                        
                        Text("Welcome Back")
                            .font(.system(size: 32, weight: .bold, design: .rounded))
                            .foregroundColor(.primary)
                        
                        Text("Sign in to continue")
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
                                if !email.isEmpty && !password.isEmpty {
                                    handleLogin()
                                }
                            }
                            .focused($focusedField, equals: .password)
                            .textContentType(.password)
                            
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
                                .frame(height: 50)
                            }
                            .buttonStyle(PrimaryActionButtonStyle())
                            .disabled(isLoading || email.isEmpty || password.isEmpty)
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
                    
                    // Social Sign In Buttons
                    VStack(spacing: 12) {
                        SocialSignInButton(
                            title: "Continue with Apple",
                            icon: "apple.logo",
                            backgroundColor: .black,
                            foregroundColor: .white
                        ) {
                            // TODO: Implement Apple sign-in
                            lightHapticFeedback()
                        }
                        
                        SocialSignInButton(
                            title: "Continue with Google",
                            icon: "globe",
                            backgroundColor: .white,
                            foregroundColor: .black
                        ) {
                            // TODO: Implement Google sign-in
                            lightHapticFeedback()
                        }
                    }
                    .padding(.horizontal, 24)
                    
                    // Register Link
                    HStack {
                        Text("Don't have an account?")
                            .font(.system(size: 15))
                            .foregroundColor(.secondary)
                        
                        Button("Sign Up") {
                            lightHapticFeedback()
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
            // Small delay to feel more natural
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
                focusedField = .email
            }
        }
    }
    
    private func handleLogin() {
        lightHapticFeedback()
        focusedField = nil
        isLoading = true
        
        Task {
            do {
                try await authService.signIn(email: email, password: password)
                if let user = Auth.auth().currentUser {
                    await MainActor.run {
                        successHapticFeedback()
                        session.startSession(userId: user.uid)
                        onLogin?(user.uid)
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

struct NativeTextField: View {
    let title: String
    @Binding var text: String
    let isSecure: Bool
    let keyboardType: UIKeyboardType
    let isFocused: Bool
    let onCommit: () -> Void
    
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(.system(size: 14, weight: .medium))
                .foregroundColor(isFocused ? .blue : .secondary)
                .animation(.easeInOut(duration: 0.2), value: isFocused)
            
            Group {
                if isSecure {
                    SecureField("", text: $text, onCommit: onCommit)
                } else {
                    TextField("", text: $text, onCommit: onCommit)
                        .keyboardType(keyboardType)
                }
            }
            .font(.system(size: 16, weight: .medium))
            .padding(.horizontal, 16)
            .padding(.vertical, 16)
            .background(
                RoundedRectangle(cornerRadius: 12)
                    .fill(Color(.systemGray6))
                    .overlay(
                        RoundedRectangle(cornerRadius: 12)
                            .stroke(isFocused ? Color.blue : Color.clear, lineWidth: 2)
                    )
            )
            .animation(.easeInOut(duration: 0.2), value: isFocused)
        }
    }
}

struct SocialSignInButton: View {
    let title: String
    let icon: String
    let backgroundColor: Color
    let foregroundColor: Color
    let action: () -> Void
    
    var body: some View {
        Button(action: action) {
            HStack(spacing: 12) {
                Image(systemName: icon)
                    .font(.system(size: 16, weight: .medium))
                
                Text(title)
                    .font(.system(size: 16, weight: .medium))
                
                Spacer()
            }
            .foregroundColor(foregroundColor)
            .padding(.horizontal, 20)
            .padding(.vertical, 16)
            .frame(height: 52)
            .background(backgroundColor)
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .stroke(Color(.systemGray4), lineWidth: backgroundColor == .white ? 1 : 0)
            )
            .cornerRadius(12)
        }
        .buttonStyle(PlainButtonStyle())
        .scaleEffect(1.0)
        .animation(.easeInOut(duration: 0.1), value: false)
    }
}

struct LoginView_Previews: PreviewProvider {
    static var previews: some View {
        LoginView()
    }
} 