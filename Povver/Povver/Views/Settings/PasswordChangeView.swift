import SwiftUI
import FirebaseAuth

/// Sheet for changing password (email/password users) or setting a password (SSO-only users).
/// "Set Password" mode links email/password as a new provider to the SSO account.
struct PasswordChangeView: View {
    let hasEmailProvider: Bool

    @ObservedObject private var authService = AuthService.shared
    @Environment(\.dismiss) private var dismiss
    @State private var currentPassword = ""
    @State private var newPassword = ""
    @State private var confirmPassword = ""
    @State private var errorMessage: String?
    @State private var isLoading = false
    @State private var isSuccess = false

    private var title: String {
        hasEmailProvider ? "Change Password" : "Set Password"
    }

    private var isValid: Bool {
        if hasEmailProvider {
            return !currentPassword.isEmpty && newPassword.count >= 6 && newPassword == confirmPassword
        } else {
            return newPassword.count >= 6 && newPassword == confirmPassword
        }
    }

    private var validationMessage: String? {
        if !newPassword.isEmpty && newPassword.count < 6 {
            return "Password must be at least 6 characters."
        }
        if !confirmPassword.isEmpty && newPassword != confirmPassword {
            return "Passwords do not match."
        }
        return nil
    }

    var body: some View {
        SheetScaffold(
            title: title,
            doneTitle: nil,
            onCancel: { dismiss() }
        ) {
            VStack(spacing: Space.xl) {
                if isSuccess {
                    successState
                } else {
                    passwordForm
                }

                Spacer()
            }
            .padding(.top, Space.lg)
        }
        .presentationDetents([.medium])
    }

    // MARK: - Password Form

    private var passwordForm: some View {
        VStack(spacing: Space.md) {
            if hasEmailProvider {
                secureTextField("Current Password", text: $currentPassword)
            }

            secureTextField("New Password", text: $newPassword)
            secureTextField("Confirm Password", text: $confirmPassword)

            if let message = validationMessage {
                Text(message)
                    .textStyle(.caption)
                    .foregroundColor(.destructive)
                    .padding(.horizontal, Space.lg)
            }

            if let errorMessage = errorMessage {
                Text(errorMessage)
                    .textStyle(.caption)
                    .foregroundColor(.destructive)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, Space.lg)
            }

            PovverButton(hasEmailProvider ? "Update Password" : "Set Password", style: .primary) {
                Task { await savePassword() }
            }
            .disabled(!isValid || isLoading)
            .padding(.horizontal, Space.lg)
        }
    }

    // MARK: - Success State

    private var successState: some View {
        VStack(spacing: Space.lg) {
            Image(systemName: "checkmark.circle.fill")
                .font(.system(size: 48))
                .foregroundColor(.accent)

            Text(hasEmailProvider ? "Password updated successfully." : "Password set. You can now sign in with email and password.")
                .textStyle(.secondary)
                .foregroundColor(.textSecondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, Space.lg)

            PovverButton("Done", style: .primary) {
                dismiss()
            }
            .padding(.horizontal, Space.lg)
        }
    }

    // MARK: - Helpers

    @ViewBuilder
    private func secureTextField(_ placeholder: String, text: Binding<String>) -> some View {
        SecureField(placeholder, text: text)
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
            .padding(.horizontal, Space.lg)
    }

    // MARK: - Actions

    private func savePassword() async {
        isLoading = true
        errorMessage = nil
        do {
            if hasEmailProvider {
                try await authService.changePassword(currentPassword: currentPassword, newPassword: newPassword)
            } else {
                try await authService.setPassword(newPassword)
            }
            isSuccess = true
        } catch {
            errorMessage = AuthService.friendlyAuthError(error)
        }
        isLoading = false
    }
}
