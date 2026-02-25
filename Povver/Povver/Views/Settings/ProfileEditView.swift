import SwiftUI

/// Profile editing screen — combines Account + Body Metrics from the old ProfileView.
/// Accessed via NavigationLink from MoreView's profile card.
struct ProfileEditView: View {
    @ObservedObject private var authService = AuthService.shared

    @State private var user: User?
    @State private var userAttributes: UserAttributes?
    @State private var isLoading = true
    @State private var sessionCount = 0
    @State private var linkedProviders: [AuthProvider] = []

    // Edit sheets
    @State private var showingNicknameEditor = false
    @State private var showingHeightEditor = false
    @State private var showingWeightEditor = false
    @State private var showingFitnessLevelPicker = false
    @State private var showingEmailChange = false
    @State private var showingPasswordChange = false

    // Edit values
    @State private var editingNickname = ""
    @State private var editingHeight: Double = 170
    @State private var editingWeight: Double = 70
    @State private var editingFitnessLevel = ""

    @State private var errorMessage: String?

    private var weightUnit: WeightUnit { UserService.shared.weightUnit }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Space.lg) {
                // Header
                profileHeader

                // Account Section
                sectionHeader("Account")
                accountSection

                // Body Metrics Section
                sectionHeader("Body Metrics")
                bodyMetricsSection

                // Error banner
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
        .navigationTitle("Profile")
        .navigationBarTitleDisplayMode(.inline)
        .task {
            await loadProfile()
        }
        .sheet(isPresented: $showingNicknameEditor) {
            nicknameEditorSheet
        }
        .sheet(isPresented: $showingHeightEditor) {
            heightEditorSheet
        }
        .sheet(isPresented: $showingWeightEditor) {
            weightEditorSheet
        }
        .sheet(isPresented: $showingFitnessLevelPicker) {
            fitnessLevelPickerSheet
        }
        .sheet(isPresented: $showingEmailChange) {
            EmailChangeView(
                hasEmailProvider: linkedProviders.contains(.email),
                providerDisplayName: linkedProviders.first(where: { $0 != .email })?.displayName ?? "your provider"
            )
        }
        .sheet(isPresented: $showingPasswordChange) {
            PasswordChangeView(hasEmailProvider: linkedProviders.contains(.email))
        }
    }

    // MARK: - Profile Header

    private var profileHeader: some View {
        VStack(alignment: .leading, spacing: Space.md) {
            HStack(spacing: Space.md) {
                ZStack {
                    Circle()
                        .fill(Color.accent.opacity(0.15))
                        .frame(width: 64, height: 64)

                    Text(initials)
                        .font(.system(size: 24, weight: .semibold))
                        .foregroundColor(Color.accent)
                }

                VStack(alignment: .leading, spacing: 4) {
                    Text(displayName)
                        .font(.system(size: 20, weight: .bold))
                        .foregroundColor(Color.textPrimary)

                    if let email = user?.email ?? authService.currentUser?.email,
                       !email.hasSuffix("@privaterelay.appleid.com") {
                        Text(email)
                            .font(.system(size: 14))
                            .foregroundColor(Color.textSecondary)
                    }
                }

                Spacer()
            }

            HStack(spacing: Space.lg) {
                if let createdAt = user?.createdAt {
                    statItem(value: formatMemberSince(createdAt), label: "Member since")
                }

                statItem(value: "\(sessionCount)", label: "Sessions")
            }
        }
        .padding(Space.lg)
    }

    // MARK: - Account Section

    private var accountSection: some View {
        VStack(spacing: 0) {
            if linkedProviders.contains(.email) {
                ProfileRow(
                    icon: "envelope",
                    title: "Email",
                    value: user?.email ?? authService.currentUser?.email ?? "-",
                    isEditable: true
                ) {
                    showingEmailChange = true
                }

                Divider().padding(.leading, 56)
            }

            ProfileRow(
                icon: "person",
                title: "Nickname",
                value: user?.name ?? "Not set",
                isEditable: true
            ) {
                editingNickname = user?.name ?? ""
                showingNicknameEditor = true
            }
        }
        .background(Color.surface)
        .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.medium))
        .padding(.horizontal, Space.lg)
    }

    // MARK: - Body Metrics Section

    private var bodyMetricsSection: some View {
        VStack(spacing: 0) {
            ProfileRow(
                icon: "ruler",
                title: "Height",
                value: formatHeight(userAttributes?.height),
                isEditable: true
            ) {
                editingHeight = userAttributes?.height ?? 170
                showingHeightEditor = true
            }

            Divider().padding(.leading, 56)

            ProfileRow(
                icon: "scalemass",
                title: "Weight",
                value: formatWeight(userAttributes?.weight),
                isEditable: true
            ) {
                // Display weight in user's preferred unit for editing
                let weightKg = userAttributes?.weight ?? 70
                editingWeight = WeightFormatter.display(weightKg, unit: weightUnit)
                showingWeightEditor = true
            }

            Divider().padding(.leading, 56)

            ProfileRow(
                icon: "flame",
                title: "Fitness Level",
                value: userAttributes?.fitnessLevel?.capitalized ?? "Not set",
                isEditable: true
            ) {
                editingFitnessLevel = userAttributes?.fitnessLevel ?? ""
                showingFitnessLevelPicker = true
            }
        }
        .background(Color.surface)
        .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.medium))
        .padding(.horizontal, Space.lg)
    }

    // MARK: - Edit Sheets

    private var nicknameEditorSheet: some View {
        SheetScaffold(
            title: "Edit Nickname",
            doneTitle: "Save",
            onCancel: { showingNicknameEditor = false },
            onDone: {
                Task { await saveNickname() }
                showingNicknameEditor = false
            }
        ) {
            VStack(spacing: Space.lg) {
                TextField("Nickname", text: $editingNickname)
                    .textFieldStyle(.roundedBorder)
                    .padding()

                Spacer()
            }
        }
        .presentationDetents([.medium])
    }

    private var heightEditorSheet: some View {
        SheetScaffold(
            title: "Edit Height",
            doneTitle: "Save",
            onCancel: { showingHeightEditor = false },
            onDone: {
                Task { await saveHeight() }
                showingHeightEditor = false
            }
        ) {
            VStack(spacing: Space.lg) {
                Text("\(Int(editingHeight)) cm")
                    .font(.system(size: 36, weight: .bold).monospacedDigit())
                    .foregroundColor(Color.textPrimary)

                Slider(value: $editingHeight, in: 100...250, step: 1)
                    .padding()

                Spacer()
            }
            .padding(.top, Space.xl)
        }
        .presentationDetents([.medium])
    }

    private var weightEditorSheet: some View {
        let minWeight = weightUnit == .lbs ? 66.0 : 30.0  // ~66lbs = 30kg
        let maxWeight = weightUnit == .lbs ? 440.0 : 200.0  // ~440lbs = 200kg
        let step = weightUnit == .lbs ? 1.0 : 0.5

        return SheetScaffold(
            title: "Edit Weight",
            doneTitle: "Save",
            onCancel: { showingWeightEditor = false },
            onDone: {
                Task { await saveWeight() }
                showingWeightEditor = false
            }
        ) {
            VStack(spacing: Space.lg) {
                Text(String(format: "%.1f \(weightUnit.label)", editingWeight))
                    .font(.system(size: 36, weight: .bold).monospacedDigit())
                    .foregroundColor(Color.textPrimary)

                Slider(value: $editingWeight, in: minWeight...maxWeight, step: step)
                    .padding()

                Spacer()
            }
            .padding(.top, Space.xl)
        }
        .presentationDetents([.medium])
    }

    private var fitnessLevelPickerSheet: some View {
        SheetScaffold(
            title: "Fitness Level",
            doneTitle: nil,
            onCancel: { showingFitnessLevelPicker = false }
        ) {
            List {
                ForEach(["beginner", "intermediate", "advanced"], id: \.self) { level in
                    Button {
                        editingFitnessLevel = level
                        Task { await saveFitnessLevel(level) }
                        showingFitnessLevelPicker = false
                    } label: {
                        HStack {
                            Text(level.capitalized)
                                .foregroundColor(Color.textPrimary)
                            Spacer()
                            if editingFitnessLevel == level {
                                Image(systemName: "checkmark")
                                    .foregroundColor(Color.accent)
                            }
                        }
                    }
                }
            }
        }
        .presentationDetents([.medium])
    }

    // MARK: - Helpers

    private func sectionHeader(_ title: String) -> some View {
        Text(title.uppercased())
            .font(.system(size: 12, weight: .semibold))
            .foregroundColor(Color.textSecondary)
            .padding(.horizontal, Space.lg)
            .padding(.top, Space.md)
    }

    private func statItem(value: String, label: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(value)
                .font(.system(size: 14, weight: .semibold))
                .foregroundColor(Color.textPrimary)
            Text(label)
                .font(.system(size: 12))
                .foregroundColor(Color.textSecondary)
        }
    }

    private var displayName: String {
        if let name = user?.name, !name.isEmpty {
            return name
        }
        if let email = user?.email ?? authService.currentUser?.email,
           !email.hasSuffix("@privaterelay.appleid.com") {
            return email.components(separatedBy: "@").first ?? email
        }
        return "User"
    }

    private var initials: String {
        let name = displayName
        let parts = name.components(separatedBy: " ")
        if parts.count >= 2 {
            return "\(parts[0].prefix(1))\(parts[1].prefix(1))".uppercased()
        }
        return String(name.prefix(2)).uppercased()
    }

    private func formatMemberSince(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.dateFormat = "MMM yyyy"
        return formatter.string(from: date)
    }

    private func formatHeight(_ height: Double?) -> String {
        guard let height = height else { return "Not set" }
        return "\(Int(height)) cm"
    }

    private func formatWeight(_ weight: Double?) -> String {
        guard let weight = weight else { return "Not set" }
        return WeightFormatter.format(weight, unit: weightUnit)
    }

    // MARK: - Data Loading

    private func loadProfile() async {
        guard let userId = authService.currentUser?.uid else {
            isLoading = false
            return
        }

        await authService.reloadCurrentUser()
        linkedProviders = authService.linkedProviders

        do {
            user = try await UserRepository.shared.getUser(userId: userId)
        } catch {
            print("[ProfileEditView] Failed to load user: \(error)")
        }

        do {
            userAttributes = try await UserRepository.shared.getUserAttributes(userId: userId)
        } catch {
            print("[ProfileEditView] Failed to load user attributes: \(error)")
        }

        do {
            sessionCount = try await WorkoutRepository().getWorkoutCount(userId: userId)
        } catch {
            // Non-critical — shows 0 sessions on failure
        }

        isLoading = false
    }

    // MARK: - Save Methods

    private func saveNickname() async {
        guard let userId = authService.currentUser?.uid else { return }
        errorMessage = nil

        do {
            try await UserRepository.shared.updateUserProfile(
                userId: userId,
                name: editingNickname,
                email: user?.email ?? ""
            )
            user?.name = editingNickname
        } catch {
            errorMessage = "Failed to save nickname. Please try again."
        }
    }

    private func saveHeight() async {
        guard let userId = authService.currentUser?.uid else { return }
        errorMessage = nil

        var attrs = userAttributes ?? UserAttributes(
            id: userId,
            fitnessGoal: nil,
            fitnessLevel: nil,
            equipment: nil,
            height: nil,
            weight: nil,
            workoutFrequency: nil,
            lastUpdated: nil
        )
        attrs.height = Double(Int(editingHeight))

        do {
            try await UserRepository.shared.saveUserAttributes(attrs)
            userAttributes = attrs
            AnalyticsService.shared.bodyMetricsUpdated(field: "height")
        } catch {
            errorMessage = "Failed to save height. Please try again."
        }
    }

    private func saveWeight() async {
        guard let userId = authService.currentUser?.uid else { return }
        errorMessage = nil

        var attrs = userAttributes ?? UserAttributes(
            id: userId,
            fitnessGoal: nil,
            fitnessLevel: nil,
            equipment: nil,
            height: nil,
            weight: nil,
            workoutFrequency: nil,
            lastUpdated: nil
        )
        // Convert user's preferred unit back to kg for storage
        let weightKg = WeightFormatter.toKg(editingWeight, from: weightUnit)
        attrs.weight = (weightKg * 10).rounded() / 10

        do {
            try await UserRepository.shared.saveUserAttributes(attrs)
            userAttributes = attrs
            AnalyticsService.shared.bodyMetricsUpdated(field: "weight")
        } catch {
            errorMessage = "Failed to save weight. Please try again."
        }
    }

    private func saveFitnessLevel(_ level: String) async {
        guard let userId = authService.currentUser?.uid else { return }
        errorMessage = nil

        var attrs = userAttributes ?? UserAttributes(
            id: userId,
            fitnessGoal: nil,
            fitnessLevel: nil,
            equipment: nil,
            height: nil,
            weight: nil,
            workoutFrequency: nil,
            lastUpdated: nil
        )
        attrs.fitnessLevel = level

        do {
            try await UserRepository.shared.saveUserAttributes(attrs)
            userAttributes = attrs
            AnalyticsService.shared.bodyMetricsUpdated(field: "fitness_level")
        } catch {
            errorMessage = "Failed to save fitness level. Please try again."
        }
    }
}
