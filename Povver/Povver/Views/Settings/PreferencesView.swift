import SwiftUI

/// Preferences screen — timezone and week start settings.
/// Accessed via NavigationLink from MoreView.
struct PreferencesView: View {
    @ObservedObject private var authService = AuthService.shared

    @State private var user: User?
    @State private var errorMessage: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Space.lg) {
                sectionHeader("General")

                VStack(spacing: 0) {
                    ProfileRow(
                        icon: "globe",
                        title: "Timezone",
                        value: user?.timeZone ?? TimeZone.current.identifier
                    )

                    Divider().padding(.leading, 56)

                    ProfileRowToggle(
                        icon: "calendar",
                        title: "Week Starts On Monday",
                        isOn: Binding(
                            get: { user?.weekStartsOnMonday ?? true },
                            set: { newValue in
                                Task { await updateWeekStart(newValue) }
                            }
                        )
                    )
                }
                .background(Color.surface)
                .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.medium))
                .padding(.horizontal, Space.lg)

                if let errorMessage = errorMessage {
                    Text(errorMessage)
                        .textStyle(.caption)
                        .foregroundColor(.destructive)
                        .padding(.horizontal, Space.lg)
                }

                Spacer(minLength: Space.xxl)
            }
        }
        .background(Color.bg)
        .navigationTitle("Preferences")
        .navigationBarTitleDisplayMode(.inline)
        .task {
            await loadUser()
        }
    }

    // MARK: - Helpers

    private func sectionHeader(_ title: String) -> some View {
        Text(title.uppercased())
            .font(.system(size: 12, weight: .semibold))
            .foregroundColor(Color.textSecondary)
            .padding(.horizontal, Space.lg)
            .padding(.top, Space.md)
    }

    private func loadUser() async {
        guard let userId = authService.currentUser?.uid else { return }
        do {
            user = try await UserRepository.shared.getUser(userId: userId)
        } catch {
            print("[PreferencesView] Failed to load user: \(error)")
        }
    }

    private func updateWeekStart(_ startsOnMonday: Bool) async {
        guard let userId = authService.currentUser?.uid else { return }
        errorMessage = nil

        do {
            try await UserRepository.shared.updateUserProfile(
                userId: userId,
                name: user?.name ?? "",
                email: user?.email ?? "",
                weekStartsOnMonday: startsOnMonday
            )
            user?.weekStartsOnMonday = startsOnMonday
            AnalyticsService.shared.preferenceChanged(preference: "week_start", value: startsOnMonday ? "monday" : "sunday")
        } catch {
            errorMessage = "Failed to update preference. Please try again."
        }
    }
}
