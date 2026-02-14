import SwiftUI

/// Sheet for sending a password reset email.
/// Presented from the "Forgot Password?" link on the login screen.
/// Design matches the branded auth flow (Login/Register) rather than settings sheets.
struct ForgotPasswordView: View {
    var prefillEmail: String = ""

    @ObservedObject private var authService = AuthService.shared
    @Environment(\.dismiss) private var dismiss
    @State private var email = ""
    @State private var errorMessage: String?
    @State private var isLoading = false
    @State private var resetSent = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: Space.xl) {
                    Spacer(minLength: Space.xxl)

                    if resetSent {
                        sentState
                    } else {
                        formState
                    }

                    Spacer(minLength: Space.xxl)
                }
                .padding(.horizontal, Space.lg)
            }
            .background(Color.bg.ignoresSafeArea())
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button {
                        dismiss()
                    } label: {
                        Image(systemName: "xmark")
                            .font(.system(size: 14, weight: .semibold))
                            .foregroundColor(.textSecondary)
                            .frame(width: 32, height: 32)
                            .background(Color.surface)
                            .clipShape(Circle())
                    }
                }
            }
        }
        .presentationDragIndicator(.hidden)
        .presentationDetents([.large])
        .presentationBackground(Color.bg)
        .onAppear {
            if email.isEmpty {
                email = prefillEmail
            }
        }
    }

    // MARK: - Form State

    private var formState: some View {
        VStack(spacing: Space.xl) {
            // Icon
            Image(systemName: "key.fill")
                .font(.system(size: 40))
                .foregroundColor(.accent)
                .frame(width: 80, height: 80)
                .background(Color.accentMuted)
                .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.radiusCard))

            // Header
            VStack(spacing: Space.sm) {
                Text("Reset Password")
                    .textStyle(.screenTitle)
                    .foregroundColor(.textPrimary)

                Text("Enter your email address and we'll send you a link to create a new password.")
                    .textStyle(.secondary)
                    .foregroundColor(.textSecondary)
                    .multilineTextAlignment(.center)
            }

            // Email field
            TextField("Email", text: $email)
                .keyboardType(.emailAddress)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
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

            if let errorMessage = errorMessage {
                Text(errorMessage)
                    .textStyle(.caption)
                    .foregroundColor(.destructive)
                    .multilineTextAlignment(.center)
            }

            PovverButton("Send Reset Link", style: .primary) {
                Task { await sendReset() }
            }
            .disabled(email.isEmpty || isLoading)
        }
    }

    // MARK: - Sent State

    private var sentState: some View {
        VStack(spacing: Space.xl) {
            // Icon
            Image(systemName: "envelope.open.fill")
                .font(.system(size: 40))
                .foregroundColor(.accent)
                .frame(width: 80, height: 80)
                .background(Color.accentMuted)
                .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.radiusCard))

            // Header
            VStack(spacing: Space.sm) {
                Text("Check Your Inbox")
                    .textStyle(.screenTitle)
                    .foregroundColor(.textPrimary)

                Text("We sent a password reset link to")
                    .textStyle(.secondary)
                    .foregroundColor(.textSecondary)

                Text(email)
                    .textStyle(.bodyStrong)
                    .foregroundColor(.textPrimary)

                Text("Open the link in the email to set a new password. It may take a minute to arrive.")
                    .textStyle(.secondary)
                    .foregroundColor(.textSecondary)
                    .multilineTextAlignment(.center)
                    .padding(.top, Space.xs)
            }

            PovverButton("Back to Login", style: .primary) {
                dismiss()
            }

            Button {
                resetSent = false
                errorMessage = nil
            } label: {
                Text("Didn't receive it? Try again")
                    .textStyle(.caption)
                    .foregroundColor(.accent)
            }
        }
    }

    // MARK: - Actions

    private func sendReset() async {
        isLoading = true
        errorMessage = nil
        do {
            try await authService.sendPasswordReset(email: email)
            resetSent = true
        } catch {
            errorMessage = AuthService.friendlyAuthError(error)
        }
        isLoading = false
    }
}
