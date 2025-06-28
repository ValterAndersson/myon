import SwiftUI
import FirebaseFirestore

struct OnboardingView: View {
    let userId: String
    var onComplete: (() -> Void)? = nil
    @State private var currentStep = 0
    @State private var fitnessGoal = ""
    @State private var fitnessLevel = ""
    @State private var equipment = ""
    @State private var height = ""
    @State private var weight = ""
    @State private var workoutFrequency = ""
    @State private var isSaving = false
    @State private var error: Error?
    @State private var name = ""
    @State private var heightFormat = "centimeter"
    @State private var weightFormat = "kilograms"
    
    private let fitnessGoals = ["Lose Weight", "Build Muscle", "Improve Fitness", "Maintain Health"]
    private let fitnessLevels = ["Beginner", "Intermediate", "Advanced"]
    private let equipmentOptions = ["None", "Basic (Dumbbells)", "Full Gym", "Free weights (barbells, dumbbells)", "Machines", "Bands", "Bodyweight only", "Other"]
    private let workoutFrequencies = ["1-2 times/week", "3-4 times/week", "5+ times/week"]
    private let heightFormats = ["centimeter", "feet"]
    private let weightFormats = ["kilograms", "pounds"]
    
    var body: some View {
        NavigationView {
            VStack {
                if currentStep == 0 {
                    nameEntryView
                } else if currentStep == 1 {
                    goalSelectionView
                } else if currentStep == 2 {
                    levelSelectionView
                } else if currentStep == 3 {
                    equipmentSelectionView
                } else if currentStep == 4 {
                    measurementsView
                } else if currentStep == 5 {
                    frequencySelectionView
                }
            }
            .navigationTitle("Welcome to MYON")
            .navigationBarTitleDisplayMode(.inline)
        }
    }
    
    private var nameEntryView: some View {
        VStack(spacing: 20) {
            Text("What's your name?")
                .font(.title2)
                .multilineTextAlignment(.center)
            TextField("Name", text: $name)
                .textFieldStyle(RoundedBorderTextFieldStyle())
            Button("Next") {
                currentStep += 1
            }
            .disabled(name.isEmpty)
        }
        .padding()
    }
    
    private var goalSelectionView: some View {
        VStack(spacing: 20) {
            Text("What's your main fitness goal?")
                .font(.title2)
                .multilineTextAlignment(.center)
            Picker("Goal", selection: $fitnessGoal) {
                ForEach(fitnessGoals, id: \.self) { Text($0) }
            }
            .pickerStyle(.menu)
            Button("Next") {
                currentStep += 1
            }
            .disabled(fitnessGoal.isEmpty)
        }
        .padding()
    }
    
    private var levelSelectionView: some View {
        VStack(spacing: 20) {
            Text("What's your current fitness level?")
                .font(.title2)
                .multilineTextAlignment(.center)
            Picker("Level", selection: $fitnessLevel) {
                ForEach(fitnessLevels, id: \.self) { Text($0) }
            }
            .pickerStyle(.menu)
            Button("Next") {
                currentStep += 1
            }
            .disabled(fitnessLevel.isEmpty)
        }
        .padding()
    }
    
    private var equipmentSelectionView: some View {
        VStack(spacing: 20) {
            Text("What equipment do you have access to?")
                .font(.title2)
                .multilineTextAlignment(.center)
            Picker("Equipment", selection: $equipment) {
                ForEach(equipmentOptions, id: \.self) { Text($0) }
            }
            .pickerStyle(.menu)
            Button("Next") {
                currentStep += 1
            }
            .disabled(equipment.isEmpty)
        }
        .padding()
    }
    
    private var measurementsView: some View {
        VStack(spacing: 20) {
            Text("Enter your measurements")
                .font(.title2)
                .multilineTextAlignment(.center)
            HStack {
                TextField("Height", text: $height)
                    .keyboardType(.decimalPad)
                    .frame(width: 80)
                    .textFieldStyle(RoundedBorderTextFieldStyle())
                Picker("", selection: $heightFormat) {
                    ForEach(heightFormats, id: \.self) { Text($0) }
                }
                .pickerStyle(.menu)
            }
            HStack {
                TextField("Weight", text: $weight)
                    .keyboardType(.decimalPad)
                    .frame(width: 80)
                    .textFieldStyle(RoundedBorderTextFieldStyle())
                Picker("", selection: $weightFormat) {
                    ForEach(weightFormats, id: \.self) { Text($0) }
                }
                .pickerStyle(.menu)
            }
            Button("Next") {
                currentStep += 1
            }
            .disabled(height.isEmpty || weight.isEmpty)
        }
        .padding()
    }
    
    private var frequencySelectionView: some View {
        VStack(spacing: 20) {
            Text("How many times per week do you plan to work out?")
                .font(.title2)
                .multilineTextAlignment(.center)
            TextField("Frequency", text: $workoutFrequency)
                .textFieldStyle(RoundedBorderTextFieldStyle())
                .keyboardType(.numberPad)
            Button("Finish") {
                saveUserAttributes()
            }
            .disabled(workoutFrequency.isEmpty)
        }
        .padding()
        .overlay {
            if isSaving {
                ProgressView("Saving...")
                    .padding()
                    .background(Color(.systemBackground))
                    .cornerRadius(10)
                    .shadow(radius: 10)
            }
        }
        .alert("Error", isPresented: .constant(error != nil)) {
            Button("OK") {
                error = nil
            }
        } message: {
            if let error = error {
                Text(error.localizedDescription)
            }
        }
    }
    
    private func saveUserAttributes() {
        isSaving = true

        let attributes = UserAttributes(
            id: userId,
            fitnessGoal: fitnessGoal,
            fitnessLevel: fitnessLevel,
            equipment: equipment,
            height: Double(height) ?? 0,
            weight: Double(weight) ?? 0,
            workoutFrequency: Int(workoutFrequency) ?? 0,
            lastUpdated: Date()
        )

        Task {
            do {
                // Save name to user document
                let userRef = Firestore.firestore().collection("users").document(userId)
                try await userRef.setData(["name": name], merge: true)
                // Save attributes with formats
                let attrRef = userRef.collection("user_attributes").document(userId)
                var attrData = try Firestore.Encoder().encode(attributes) as! [String: Any]
                attrData["height_format"] = heightFormat
                attrData["weight_format"] = weightFormat
                try await attrRef.setData(attrData)
                // Call onComplete to signal onboarding is done
                DispatchQueue.main.async {
                    onComplete?()
                }
            } catch {
                self.error = error
            }
            isSaving = false
        }
    }
} 