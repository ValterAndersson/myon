import SwiftUI
import FirebaseAuth

/// Sheet for changing the user's email address.
/// SSO-only users see a disabled state explaining email is managed by their provider.
/// Email/password users get a working change flow with verification.
struct EmailChangeView: View {
    let hasEmailProvider: Bool
    let providerDisplayName: String

    @ObservedObject private var authService = AuthService.shared
    @Environment(\.dismiss) private var dismiss
    @State private var newEmail = ""
    @State private var errorMessage: String?
    @State private var isLoading = false
    @State private var verificationSent = false
    @State private var showingReauth = false

    var body: some View {
        SheetScaffold(
            title: "Email",
            doneTitle: nil,
            onCancel: { dismiss() }
        ) {
            ScrollView {
                VStack(spacing: Space.xl) {
                    Spacer(minLength: Space.lg)

                    if !hasEmailProvider {
                        ssoDisabledState
                    } else if verificationSent {
                        verificationSentState
                    } else {
                        changeEmailForm
                    }

                    Spacer()
                }
            }
        }
        .presentationDetents([.medium])
        .sheet(isPresented: $showingReauth) {
            ReauthenticationView(
                providers: authService.linkedProviders,
                onSuccess: { Task { await sendVerification() } }
            )
        }
    }

    // MARK: - SSO Disabled State

    private var ssoDisabledState: some View {
        VStack(spacing: Space.lg) {
            Image(systemName: "lock.fill")
                .font(.system(size: 32))
                .foregroundColor(.textTertiary)

            Text(authService.currentUser?.email ?? "-")
                .textStyle(.body)
                .foregroundColor(.textTertiary)

            Text("Changing email is not possible when signed in with \(providerDisplayName).")
                .textStyle(.caption)
                .foregroundColor(.textTertiary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, Space.lg)
        }
        .padding(.horizontal, Space.lg)
    }

    // MARK: - Change Email Form

    private var changeEmailForm: some View {
        VStack(spacing: Space.md) {
            TextField("New email address", text: $newEmail)
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
                .padding(.horizontal, Space.lg)

            if let errorMessage = errorMessage {
                Text(errorMessage)
                    .textStyle(.caption)
                    .foregroundColor(.destructive)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, Space.lg)
            }

            PovverButton("Send Verification", style: .primary) {
                Task { await sendVerification() }
            }
            .disabled(newEmail.isEmpty || isLoading)
            .padding(.horizontal, Space.lg)
        }
    }

    // MARK: - Verification Sent State

    private var verificationSentState: some View {
        VStack(spacing: Space.lg) {
            Image(systemName: "envelope.open.fill")
                .font(.system(size: 32))
                .foregroundColor(.accent)
                .frame(width: 64, height: 64)
                .background(Color.accentMuted)
                .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.radiusControl))

            VStack(spacing: Space.sm) {
                Text("Verification Sent")
                    .textStyle(.bodyStrong)
                    .foregroundColor(.textPrimary)

                Text("We sent a verification link to")
                    .textStyle(.secondary)
                    .foregroundColor(.textSecondary)

                Text(newEmail)
                    .textStyle(.bodyStrong)
                    .foregroundColor(.textPrimary)

                Text("Click the link in the email to complete the change.")
                    .textStyle(.secondary)
                    .foregroundColor(.textSecondary)
                    .multilineTextAlignment(.center)
                    .padding(.top, Space.xs)
            }

            PovverButton("Done", style: .primary) {
                dismiss()
            }
            .padding(.horizontal, Space.lg)
        }
        .padding(.horizontal, Space.lg)
    }

    // MARK: - Actions

    private func sendVerification() async {
        isLoading = true
        errorMessage = nil
        do {
            try await authService.changeEmail(to: newEmail)
            verificationSent = true
        } catch {
            let nsError = error as NSError
            if AuthErrorCode(rawValue: nsError.code) == .requiresRecentLogin {
                showingReauth = true
            } else {
                errorMessage = AuthService.friendlyAuthError(error)
            }
        }
        isLoading = false
    }
}
