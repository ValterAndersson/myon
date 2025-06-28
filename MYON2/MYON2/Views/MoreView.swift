import SwiftUI
import FirebaseAuth
import FirebaseFirestore

struct MoreView: View {
    var onLogout: (() -> Void)? = nil
    @StateObject private var authService = AuthService.shared
    @ObservedObject private var session = SessionManager.shared
    @State private var email: String = ""
    @State private var name: String = ""
    @State private var fitnessGoal: String = ""
    @State private var fitnessLevel: String = ""
    @State private var equipment: String = ""
    @State private var height: String = ""
    @State private var weight: String = ""
    @State private var showingDeleteAlert = false
    @State private var showingSaveAlert = false
    @State private var isLoading = false
    @State private var errorMessage: String?
    @State private var workoutFrequencyString: String = ""
    @State private var heightFormat = "centimeter"
    @State private var weightFormat = "kilograms"
    private let heightFormats = ["centimeter", "feet"]
    private let weightFormats = ["kilograms", "pounds"]
    @State private var recalculationResult: String?
    @State private var showingRecalculationAlert = false
    
    private let userRepository = UserRepository()
    private let cloudFunctionService = CloudFunctionService()
    
    // Options arrays (same as onboarding)
    private let fitnessGoals = ["Lose Weight", "Build Muscle", "Improve Fitness", "Maintain Health"]
    private let fitnessLevels = ["Beginner", "Intermediate", "Advanced"]
    private let equipmentOptions = ["None", "Basic (Dumbbells)", "Full Gym", "Free weights (barbells, dumbbells)", "Machines", "Bands", "Bodyweight only", "Other"]
    
    var body: some View {
        NavigationView {
            Form {
                Section(header: Text("Account")) {
                    HStack {
                        Text("Email")
                        Spacer()
                        Text(email)
                            .foregroundColor(.secondary)
                    }
                    HStack {
                        Text("Name")
                        Spacer()
                        TextField("Name", text: $name)
                            .multilineTextAlignment(.trailing)
                            .foregroundColor(.secondary)
                    }
                }
                
                Section(header: Text("Fitness Profile")) {
                    HStack {
                        Text("Goal")
                        Spacer()
                        Picker("Goal", selection: $fitnessGoal) {
                            ForEach(fitnessGoals, id: \.self) { Text($0) }
                        }
                        .pickerStyle(.menu)
                        .frame(maxWidth: .infinity, alignment: .trailing)
                    }
                    HStack {
                        Text("Level")
                        Spacer()
                        Picker("Level", selection: $fitnessLevel) {
                            ForEach(fitnessLevels, id: \.self) { Text($0) }
                        }
                        .pickerStyle(.menu)
                        .frame(maxWidth: .infinity, alignment: .trailing)
                    }
                    HStack {
                        Text("Equipment")
                        Spacer()
                        Picker("Equipment", selection: $equipment) {
                            ForEach(equipmentOptions, id: \.self) { Text($0) }
                        }
                        .pickerStyle(.menu)
                        .frame(maxWidth: .infinity, alignment: .trailing)
                    }
                    HStack {
                        Text("Height")
                        Spacer()
                        TextField("Height", text: $height)
                            .keyboardType(.decimalPad)
                            .frame(width: 80)
                            .multilineTextAlignment(.trailing)
                            .foregroundColor(.secondary)
                        Picker("", selection: $heightFormat) {
                            ForEach(heightFormats, id: \.self) { Text($0) }
                        }
                        .pickerStyle(.menu)
                        .frame(width: 120)
                    }
                    HStack {
                        Text("Weight")
                        Spacer()
                        TextField("Weight", text: $weight)
                            .keyboardType(.decimalPad)
                            .frame(width: 80)
                            .multilineTextAlignment(.trailing)
                            .foregroundColor(.secondary)
                        Picker("", selection: $weightFormat) {
                            ForEach(weightFormats, id: \.self) { Text($0) }
                        }
                        .pickerStyle(.menu)
                        .frame(width: 120)
                    }
                    HStack {
                        Text("Frequency (times/week)")
                        Spacer()
                        TextField("Frequency", text: $workoutFrequencyString)
                            .keyboardType(.numberPad)
                            .multilineTextAlignment(.trailing)
                            .foregroundColor(.secondary)
                    }
                }
                
                Section {
                    Button("Save Changes") {
                        saveChanges()
                    }
                    .foregroundColor(.blue)
                    
                    Button("Recalculate Weekly Stats") {
                        Task {
                            await recalculateWeeklyStats()
                        }
                    }
                    .foregroundColor(.green)
                    
                    Button("Log Out") {
                        onLogout?()
                    }
                    .foregroundColor(.red)
                    
                    Button("Delete Profile") {
                        showingDeleteAlert = true
                    }
                    .foregroundColor(.red)
                }
            }
            .navigationTitle("More / Settings")
            .alert("Delete Profile", isPresented: $showingDeleteAlert) {
                Button("Cancel", role: .cancel) { }
                Button("Delete", role: .destructive) {
                    deleteProfile()
                }
            } message: {
                Text("Are you sure you want to delete your profile? This action cannot be undone.")
            }
            .alert("Save Changes", isPresented: $showingSaveAlert) {
                Button("OK", role: .cancel) { }
            } message: {
                Text("Your changes have been saved successfully.")
            }
            .alert("Weekly Stats Recalculation", isPresented: $showingRecalculationAlert) {
                Button("OK", role: .cancel) { }
            } message: {
                Text(recalculationResult ?? "")
            }
            .overlay {
                if isLoading {
                    ProgressView()
                }
            }
            .alert("Error", isPresented: .constant(errorMessage != nil)) {
                Button("OK") {
                    errorMessage = nil
                }
            } message: {
                if let errorMessage = errorMessage {
                    Text(errorMessage)
                }
            }
            .onAppear {
                loadUserData()
            }
        }
    }
    
    private func loadUserData() {
        guard let userId = session.userId else { return }
        
        isLoading = true
        Task {
            do {
                // Get user profile
                if let user = try await userRepository.getUser(userId: userId) {
                    DispatchQueue.main.async {
                        self.name = user.name ?? ""
                        self.email = user.email
                    }
                }
                
                // Get user attributes
                if let attributes = try await userRepository.getUserAttributes(userId: userId) {
                    let attrRef = Firestore.firestore().collection("users").document(userId).collection("user_attributes").document(userId)
                    let attrDoc = try await attrRef.getDocument()
                    let data = attrDoc.data() ?? [:]
                    DispatchQueue.main.async {
                        self.fitnessGoal = attributes.fitnessGoal ?? ""
                        self.fitnessLevel = attributes.fitnessLevel ?? ""
                        self.equipment = attributes.equipment ?? ""
                        self.height = attributes.height.map { String(format: "%.1f", $0) } ?? ""
                        self.weight = attributes.weight.map { String(format: "%.1f", $0) } ?? ""
                        self.heightFormat = data["height_format"] as? String ?? "centimeter"
                        self.weightFormat = data["weight_format"] as? String ?? "kilograms"
                        self.workoutFrequencyString = attributes.workoutFrequency.map { String($0) } ?? ""
                    }
                }
                
                DispatchQueue.main.async {
                    self.isLoading = false
                }
            } catch {
                DispatchQueue.main.async {
                    self.errorMessage = error.localizedDescription
                    self.isLoading = false
                }
            }
        }
    }
    
    private func saveChanges() {
        guard let userId = session.userId else { return }
        
        isLoading = true
        Task {
            do {
                // Update user profile
                try await userRepository.updateUserProfile(userId: userId, name: name, email: email)
                
                // Update user attributes
                let attributes = UserAttributes(
                    id: userId,
                    fitnessGoal: fitnessGoal,
                    fitnessLevel: fitnessLevel,
                    equipment: equipment,
                    height: Double(height),
                    weight: Double(weight),
                    workoutFrequency: Int(workoutFrequencyString) ?? 0,
                    lastUpdated: Date()
                )
                let attrRef = Firestore.firestore().collection("users").document(userId).collection("user_attributes").document(userId)
                var attrData = try Firestore.Encoder().encode(attributes) as! [String: Any]
                attrData["height_format"] = heightFormat
                attrData["weight_format"] = weightFormat
                try await attrRef.setData(attrData)
                
                DispatchQueue.main.async {
                    self.showingSaveAlert = true
                    self.isLoading = false
                }
            } catch {
                DispatchQueue.main.async {
                    self.errorMessage = error.localizedDescription
                    self.isLoading = false
                }
            }
        }
    }
    
    private func deleteProfile() {
        guard let userId = session.userId else { return }
        
        isLoading = true
        Task {
            do {
                // Delete user data from Firestore
                try await userRepository.deleteUser(userId: userId)
                
                // Delete user from Firebase Auth
                if let user = Auth.auth().currentUser {
                    try await user.delete()
                }
                
                DispatchQueue.main.async {
                    self.isLoading = false
                    self.onLogout?()
                }
            } catch {
                DispatchQueue.main.async {
                    self.errorMessage = error.localizedDescription
                    self.isLoading = false
                }
            }
        }
    }
    
    private func recalculateWeeklyStats() {
        isLoading = true
        Task {
            do {
                let result = try await cloudFunctionService.manualWeeklyStatsRecalculation()
                
                DispatchQueue.main.async {
                    self.isLoading = false
                    
                    if result.success {
                        let currentWeek = result.results.currentWeek
                        let lastWeek = result.results.lastWeek
                        
                        self.recalculationResult = "Recalculation completed successfully!\n\n" +
                            "Current Week (\(currentWeek.weekId)): \(currentWeek.workoutCount) workouts\n" +
                            "Last Week (\(lastWeek.weekId)): \(lastWeek.workoutCount) workouts\n\n" +
                            "Status: \(currentWeek.success && lastWeek.success ? "✅ All successful" : "⚠️ Some issues occurred")"
                    } else {
                        self.recalculationResult = "Recalculation failed: \(result.message)"
                    }
                    
                    self.showingRecalculationAlert = true
                }
            } catch {
                DispatchQueue.main.async {
                    self.isLoading = false
                    self.recalculationResult = "Error: \(error.localizedDescription)"
                    self.showingRecalculationAlert = true
                }
            }
        }
    }
} 