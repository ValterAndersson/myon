import SwiftUI

/// Sheet presented when a sensitive operation (email change, password change, account deletion)
/// requires fresh credentials. Shows reauthentication options based on the user's linked providers.
struct ReauthenticationView: View {
    let providers: [AuthProvider]
    let onSuccess: () -> Void

    @ObservedObject private var authService = AuthService.shared
    @Environment(\.dismiss) private var dismiss
    @State private var password = ""
    @State private var errorMessage: String?
    @State private var isLoading = false

    var body: some View {
        SheetScaffold(
            title: "Verify It's You",
            doneTitle: nil,
            onCancel: { dismiss() }
        ) {
            VStack(spacing: Space.xl) {
                Text("For your security, please sign in again.")
                    .textStyle(.secondary)
                    .foregroundColor(.textSecondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, Space.lg)

                VStack(spacing: Space.md) {
                    if providers.contains(.email) {
                        SecureField("Password", text: $password)
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

                        PovverButton("Verify", style: .primary) {
                            Task { await reauthenticateWithEmail() }
                        }
                        .disabled(password.isEmpty || isLoading)
                    }

                    if providers.contains(.google) {
                        PovverButton("Verify with Google", style: .secondary, leadingIcon: Image(systemName: "globe")) {
                            Task { await reauthenticateWithGoogle() }
                        }
                    }

                    if providers.contains(.apple) {
                        PovverButton("Verify with Apple", style: .secondary, leadingIcon: Image(systemName: "apple.logo")) {
                            Task { await reauthenticateWithApple() }
                        }
                    }
                }
                .padding(.horizontal, Space.lg)

                if let errorMessage = errorMessage {
                    Text(errorMessage)
                        .textStyle(.caption)
                        .foregroundColor(.destructive)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal, Space.lg)
                }

                Spacer()
            }
            .padding(.top, Space.lg)
        }
        .presentationDetents([.medium])
    }

    private func reauthenticateWithApple() async {
        isLoading = true
        do {
            try await authService.reauthenticateWithApple()
            onSuccess()
            dismiss()
        } catch {
            errorMessage = AuthService.friendlyAuthError(error)
        }
        isLoading = false
    }

    private func reauthenticateWithGoogle() async {
        isLoading = true
        do {
            try await authService.reauthenticateWithGoogle()
            onSuccess()
            dismiss()
        } catch {
            errorMessage = AuthService.friendlyAuthError(error)
        }
        isLoading = false
    }

    private func reauthenticateWithEmail() async {
        isLoading = true
        do {
            try await authService.reauthenticateWithEmail(password: password)
            onSuccess()
            dismiss()
        } catch {
            errorMessage = AuthService.friendlyAuthError(error)
        }
        isLoading = false
    }
}
