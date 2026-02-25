import SwiftUI

/// Preferences screen — timezone and week start settings.
/// Accessed via NavigationLink from MoreView.
struct PreferencesView: View {
    @ObservedObject private var authService = AuthService.shared
    @ObservedObject private var userService = UserService.shared

    @State private var user: User?
    @State private var errorMessage: String?
    @State private var selectedWeightUnit: WeightUnit = .kg

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

                sectionHeader("Units")

                VStack(spacing: 0) {
                    HStack(spacing: Space.md) {
                        Image(systemName: "scalemass")
                            .font(.system(size: 18))
                            .foregroundColor(Color.textSecondary)
                            .frame(width: 24)

                        Text("Weight")
                            .font(.system(size: 15))
                            .foregroundColor(Color.textPrimary)

                        Spacer()

                        Picker("", selection: $selectedWeightUnit) {
                            ForEach(WeightUnit.allCases, id: \.self) { unit in
                                Text(unit.label).tag(unit)
                            }
                        }
                        .pickerStyle(.segmented)
                        .frame(width: 100)
                        .onChange(of: selectedWeightUnit) { newValue in
                            Task { await updateWeightUnit(newValue) }
                        }
                    }
                    .padding(Space.md)
                }
                .background(Color.surface)
                .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.medium))
                .padding(.horizontal, Space.lg)

                Spacer(minLength: Space.xxl)
            }
        }
        .background(Color.bg)
        .navigationTitle("Preferences")
        .navigationBarTitleDisplayMode(.inline)
        .task {
            await loadUser()
            selectedWeightUnit = userService.weightUnit
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

    private func updateWeightUnit(_ unit: WeightUnit) async {
        guard authService.currentUser?.uid != nil else { return }
        errorMessage = nil

        do {
            let requestBody = UpdatePreferencesRequest(preferences: ["weight_format": unit.firestoreFormat])
            let _: UpdatePreferencesResponse = try await ApiClient.shared.postJSON("updateUserPreferences", body: requestBody)
            UserService.shared.reloadPreferences()
            AnalyticsService.shared.preferenceChanged(preference: "weight_unit", value: unit.rawValue)
        } catch {
            errorMessage = "Failed to update preference. Please try again."
            // Revert the picker to the previous value
            selectedWeightUnit = userService.weightUnit
        }
    }
}

// MARK: - Request/Response Types

struct UpdatePreferencesRequest: Encodable {
    let preferences: [String: String]
}

struct UpdatePreferencesResponse: Decodable {
    let success: Bool
}
