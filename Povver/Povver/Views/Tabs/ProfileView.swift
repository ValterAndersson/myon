import SwiftUI

/// Profile Tab - Account and settings
/// Contains user info, preferences, and settings with real data and editing
struct ProfileView: View {
    @ObservedObject private var authService = AuthService.shared
    
    @State private var user: User?
    @State private var userAttributes: UserAttributes?
    @State private var isLoading = true
    @State private var sessionCount = 0
    
    // Auth state
    @State private var linkedProviders: [AuthProvider] = []

    // Edit sheets
    @State private var showingNicknameEditor = false
    @State private var showingHeightEditor = false
    @State private var showingWeightEditor = false
    @State private var showingFitnessLevelPicker = false
    @State private var showingTimezonePicker = false
    @State private var showingLogoutConfirmation = false
    @State private var showingEmailChange = false
    @State private var showingPasswordChange = false
    
    // Edit values
    @State private var editingNickname = ""
    @State private var editingHeight: Double = 170
    @State private var editingWeight: Double = 70
    @State private var editingFitnessLevel = ""
    
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
                
                // Preferences Section
                sectionHeader("Preferences")
                preferencesSection
                
                // Security Section
                sectionHeader("Security")
                securitySection

                // More Section (Placeholders)
                sectionHeader("More")
                moreSection
                
                // Logout
                logoutSection
                
                Spacer(minLength: Space.xxl)
            }
        }
        .background(Color.bg)
        .navigationTitle("")
        .navigationBarTitleDisplayMode(.inline)
        .task {
            await loadProfile()
        }
        .confirmationDialog("Sign Out", isPresented: $showingLogoutConfirmation) {
            Button("Sign Out", role: .destructive) {
                logout()
            }
            Button("Cancel", role: .cancel) { }
        } message: {
            Text("Are you sure you want to sign out?")
        }
        // Edit sheets
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
                // Avatar
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
            
            // Member since + Session count
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
                editingWeight = userAttributes?.weight ?? 70
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
    
    // MARK: - Preferences Section
    
    private var preferencesSection: some View {
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
    }
    
    // MARK: - Security Section

    private var securitySection: some View {
        VStack(spacing: 0) {
            NavigationLink(destination: LinkedAccountsView()) {
                ProfileRowLinkContent(
                    icon: "lock.shield",
                    title: "Linked Accounts",
                    subtitle: "\(linkedProviders.count) sign-in method\(linkedProviders.count == 1 ? "" : "s")"
                )
            }
            .buttonStyle(PlainButtonStyle())

            Divider().padding(.leading, 56)

            Button {
                showingPasswordChange = true
            } label: {
                ProfileRowLinkContent(
                    icon: "key",
                    title: linkedProviders.contains(.email) ? "Change Password" : "Set Password",
                    subtitle: linkedProviders.contains(.email) ? "Update your password" : "Add email sign-in"
                )
            }
            .buttonStyle(PlainButtonStyle())

            Divider().padding(.leading, 56)

            NavigationLink(destination: DeleteAccountView()) {
                ProfileRowLinkContent(
                    icon: "trash",
                    title: "Delete Account",
                    subtitle: "Permanently delete your account"
                )
            }
            .buttonStyle(PlainButtonStyle())
        }
        .background(Color.surface)
        .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.medium))
        .padding(.horizontal, Space.lg)
    }

    // MARK: - More Section
    
    private var moreSection: some View {
        VStack(spacing: 0) {
            NavigationLink(destination: SubscriptionView()) {
                ProfileRowLinkContent(
                    icon: "creditcard",
                    title: "Subscription",
                    subtitle: "Manage your plan"
                )
            }
            .buttonStyle(PlainButtonStyle())
            
            Divider().padding(.leading, 56)
            
            NavigationLink(destination: DevicesPlaceholderView()) {
                ProfileRowLinkContent(
                    icon: "applewatch",
                    title: "Devices",
                    subtitle: "Connected devices"
                )
            }
            .buttonStyle(PlainButtonStyle())
            
            Divider().padding(.leading, 56)
            
            NavigationLink(destination: MemoriesPlaceholderView()) {
                ProfileRowLinkContent(
                    icon: "brain",
                    title: "Memories",
                    subtitle: "What Coach knows about you"
                )
            }
            .buttonStyle(PlainButtonStyle())
        }
        .background(Color.surface)
        .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.medium))
        .padding(.horizontal, Space.lg)
    }
    
    // MARK: - Logout Section
    
    private var logoutSection: some View {
        Button {
            showingLogoutConfirmation = true
        } label: {
            HStack {
                Image(systemName: "rectangle.portrait.and.arrow.right")
                    .font(.system(size: 18))
                    .foregroundColor(Color.destructive)
                
                Text("Sign Out")
                    .font(.system(size: 16, weight: .medium))
                    .foregroundColor(Color.destructive)
                
                Spacer()
            }
            .padding(Space.md)
            .background(Color.surface)
            .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.medium))
        }
        .buttonStyle(PlainButtonStyle())
        .padding(.horizontal, Space.lg)
        .padding(.top, Space.md)
    }
    
    // MARK: - Edit Sheets - uses SheetScaffold for v1.1 consistency
    
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
        SheetScaffold(
            title: "Edit Weight",
            doneTitle: "Save",
            onCancel: { showingWeightEditor = false },
            onDone: {
                Task { await saveWeight() }
                showingWeightEditor = false
            }
        ) {
            VStack(spacing: Space.lg) {
                Text(String(format: "%.1f kg", editingWeight))
                    .font(.system(size: 36, weight: .bold).monospacedDigit())
                    .foregroundColor(Color.textPrimary)
                
                Slider(value: $editingWeight, in: 30...200, step: 0.5)
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
        return String(format: "%.1f kg", weight)
    }
    
    // MARK: - Data Loading
    
    private func loadProfile() async {
        guard let userId = authService.currentUser?.uid else {
            isLoading = false
            return
        }

        await authService.reloadCurrentUser()
        linkedProviders = authService.linkedProviders

        // Load user profile
        do {
            user = try await UserRepository.shared.getUser(userId: userId)
        } catch {
            print("[ProfileView] Failed to load user: \(error)")
        }
        
        // Load user attributes
        do {
            userAttributes = try await UserRepository.shared.getUserAttributes(userId: userId)
        } catch {
            print("[ProfileView] Failed to load user attributes: \(error)")
        }
        
        // Load session count
        do {
            let workouts = try await WorkoutRepository().getWorkouts(userId: userId)
            sessionCount = workouts.count
        } catch {
            print("[ProfileView] Failed to load session count: \(error)")
        }
        
        isLoading = false
    }
    
    // MARK: - Save Methods
    
    private func saveNickname() async {
        guard let userId = authService.currentUser?.uid else { return }
        
        do {
            try await UserRepository.shared.updateUserProfile(
                userId: userId,
                name: editingNickname,
                email: user?.email ?? ""
            )
            user?.name = editingNickname
        } catch {
            print("[ProfileView] Failed to save nickname: \(error)")
        }
    }
    
    private func saveHeight() async {
        guard let userId = authService.currentUser?.uid else { return }
        
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
        // Round to whole number to avoid decimal precision issues
        attrs.height = Double(Int(editingHeight))
        
        do {
            try await UserRepository.shared.saveUserAttributes(attrs)
            userAttributes = attrs
        } catch {
            print("[ProfileView] Failed to save height: \(error)")
        }
    }
    
    private func saveWeight() async {
        guard let userId = authService.currentUser?.uid else { return }
        
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
        // Round to 1 decimal place to avoid precision issues
        attrs.weight = (editingWeight * 10).rounded() / 10
        
        do {
            try await UserRepository.shared.saveUserAttributes(attrs)
            userAttributes = attrs
        } catch {
            print("[ProfileView] Failed to save weight: \(error)")
        }
    }
    
    private func saveFitnessLevel(_ level: String) async {
        guard let userId = authService.currentUser?.uid else { return }
        
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
        } catch {
            print("[ProfileView] Failed to save fitness level: \(error)")
        }
    }
    
    private func updateWeekStart(_ startsOnMonday: Bool) async {
        guard let userId = authService.currentUser?.uid else { return }
        
        do {
            try await UserRepository.shared.updateUserProfile(
                userId: userId,
                name: user?.name ?? "",
                email: user?.email ?? "",
                weekStartsOnMonday: startsOnMonday
            )
            user?.weekStartsOnMonday = startsOnMonday
        } catch {
            print("[ProfileView] Failed to update week start: \(error)")
        }
    }
    
    private func logout() {
        do {
            try authService.signOut()
        } catch {
            print("[ProfileView] Logout failed: \(error)")
        }
    }
}

// MARK: - Placeholder Views

private struct DevicesPlaceholderView: View {
    var body: some View {
        VStack(spacing: Space.lg) {
            Image(systemName: "applewatch")
                .font(.system(size: 48))
                .foregroundColor(Color.textTertiary)
            
            Text("Connected Devices")
                .font(.system(size: 20, weight: .semibold))
            
            Text("Link your Apple Watch or other devices")
                .font(.system(size: 14))
                .foregroundColor(Color.textSecondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.bg)
        .navigationTitle("Devices")
    }
}

private struct MemoriesPlaceholderView: View {
    var body: some View {
        VStack(spacing: Space.lg) {
            Image(systemName: "brain")
                .font(.system(size: 48))
                .foregroundColor(Color.textTertiary)
            
            Text("Memories")
                .font(.system(size: 20, weight: .semibold))
            
            Text("What Coach has learned about your training")
                .font(.system(size: 14))
                .foregroundColor(Color.textSecondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.bg)
        .navigationTitle("Memories")
    }
}

#if DEBUG
struct ProfileView_Previews: PreviewProvider {
    static var previews: some View {
        NavigationStack {
            ProfileView()
        }
    }
}
#endif
