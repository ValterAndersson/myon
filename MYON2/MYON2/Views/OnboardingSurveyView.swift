import SwiftUI
import FirebaseFirestore

struct OnboardingSurveyView: View {
    let userId: String
    var onComplete: (() -> Void)? = nil
    @State private var equipmentPreference = ""
    @State private var fitnessGoal = ""
    @State private var fitnessLevel = ""
    @State private var height = ""
    @State private var heightFormat = "centimeter"
    @State private var weight = ""
    @State private var weightFormat = "kilograms"
    @State private var workoutsPerWeekGoal = ""
    @State private var isLoading = false
    @State private var errorMessage: String?
    
    let equipmentOptions = ["Free weights (barbells, dumbbells)", "Machines", "Bands", "Bodyweight only", "Other"]
    let fitnessGoals = ["Build muscle", "Lose weight", "Improve endurance", "General health", "Other"]
    let fitnessLevels = ["Beginner", "Intermediate", "Advanced"]
    let heightFormats = ["centimeter", "inch"]
    let weightFormats = ["kilograms", "pounds"]
    let workoutsPerWeekOptions = ["1", "2", "3", "4", "5", "6", "7"]
    
    var body: some View {
        ScrollView {
            VStack(spacing: 24) {
                Text("Tell us about yourself").font(.title2).bold()
                Picker("Equipment", selection: $equipmentPreference) {
                    ForEach(equipmentOptions, id: \ .self) { Text($0) }
                }
                .pickerStyle(.menu)
                Picker("Fitness Goal", selection: $fitnessGoal) {
                    ForEach(fitnessGoals, id: \ .self) { Text($0) }
                }
                .pickerStyle(.menu)
                Picker("Fitness Level", selection: $fitnessLevel) {
                    ForEach(fitnessLevels, id: \ .self) { Text($0) }
                }
                .pickerStyle(.menu)
                HStack {
                    TextField("Height", text: $height)
                        .keyboardType(.numberPad)
                        .frame(width: 80)
                        .textFieldStyle(RoundedBorderTextFieldStyle())
                    Picker("", selection: $heightFormat) {
                        ForEach(heightFormats, id: \ .self) { Text($0) }
                    }
                    .pickerStyle(.menu)
                }
                HStack {
                    TextField("Weight", text: $weight)
                        .keyboardType(.numberPad)
                        .frame(width: 80)
                        .textFieldStyle(RoundedBorderTextFieldStyle())
                    Picker("", selection: $weightFormat) {
                        ForEach(weightFormats, id: \ .self) { Text($0) }
                    }
                    .pickerStyle(.menu)
                }
                Picker("Workouts/Week", selection: $workoutsPerWeekGoal) {
                    ForEach(workoutsPerWeekOptions, id: \ .self) { Text($0) }
                }
                .pickerStyle(.menu)
                if let errorMessage = errorMessage {
                    Text(errorMessage).foregroundColor(.red)
                }
                Button("Submit") {
                    submitSurvey()
                }
                .disabled(isLoading || !isValid)
                if isLoading {
                    ProgressView()
                }
            }
            .padding()
        }
    }
    
    private var isValid: Bool {
        !equipmentPreference.isEmpty && !fitnessGoal.isEmpty && !fitnessLevel.isEmpty && !height.isEmpty && !heightFormat.isEmpty && !weight.isEmpty && !weightFormat.isEmpty && !workoutsPerWeekGoal.isEmpty
    }
    
    private func submitSurvey() {
        isLoading = true
        errorMessage = nil
        let db = Firestore.firestore()
        let data: [String: Any] = [
            "equipment_preference": equipmentPreference,
            "fitness_goal": fitnessGoal,
            "fitness_level": fitnessLevel,
            "height": Int(height) ?? 0,
            "height_format": heightFormat,
            "weight": Int(weight) ?? 0,
            "weight_format": weightFormat,
            "workouts_per_week_goal": Int(workoutsPerWeekGoal) ?? 0
        ]
        db.collection("users").document(userId).collection("user_attributes").document(userId).setData(data) { error in
            DispatchQueue.main.async {
                isLoading = false
                if let error = error {
                    errorMessage = error.localizedDescription
                } else {
                    onComplete?()
                }
            }
        }
    }
}

struct OnboardingSurveyView_Previews: PreviewProvider {
    static var previews: some View {
        OnboardingSurveyView(userId: "test")
    }
} 