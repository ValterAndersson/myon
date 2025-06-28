import SwiftUI

// MARK: - Shared Visual Constants for Consistency
struct WorkoutDesignSystem {
    // Colors
    static let cardBackground = Color(.systemGray6)
    static let completedBackground = Color.green.opacity(0.05)
    static let completedBorder = Color.green.opacity(0.3)
    static let primaryBlue = Color.blue
    static let destructiveRed = Color.red
    
    // Spacing
    static let cardPadding: CGFloat = 12
    static let itemSpacing: CGFloat = 8
    static let sectionSpacing: CGFloat = 16
    
    // Corner Radius
    static let cardCornerRadius: CGFloat = 12
    static let buttonCornerRadius: CGFloat = 8
    static let fieldCornerRadius: CGFloat = 6
    
    // Typography
    static let exerciseNameFont = Font.headline
    static let setNumberFont = Font.headline.weight(.semibold)
    static let labelFont = Font.caption2
    static let bodyFont = Font.system(.body, design: .monospaced)
}

// MARK: - Template Exercise Card (Simple Version)
struct TemplateExerciseCard: View {
    let exercise: WorkoutTemplateExercise
    let onRemove: () -> Void
    let onAddSet: () -> Void
    let onRemoveSet: (String) -> Void
    @StateObject private var exercisesViewModel = ExercisesViewModel()
    
    private var exerciseName: String {
        if let matchedExercise = exercisesViewModel.exercises.first(where: { $0.id == exercise.exerciseId }) {
            return matchedExercise.name
        }
        return "Unknown Exercise"
    }
    
    var body: some View {
        VStack(alignment: .leading, spacing: WorkoutDesignSystem.sectionSpacing) {
            // Exercise header
            HStack {
                Text(exerciseName.capitalized)
                    .font(WorkoutDesignSystem.exerciseNameFont)
                    .textCase(.none)
                    .foregroundColor(.primary)
                
                Spacer()
                
                Menu {
                    Button("Add Set", systemImage: "plus") {
                        onAddSet()
                    }
                    Button("Remove Exercise", systemImage: "trash", role: .destructive) {
                        onRemove()
                    }
                } label: {
                    Image(systemName: "ellipsis")
                        .foregroundColor(.gray)
                }
            }
            
            // Sets section
            VStack(alignment: .leading, spacing: WorkoutDesignSystem.itemSpacing) {
                HStack {
                    Text("Sets")
                        .font(.subheadline)
                        .fontWeight(.medium)
                    
                    Spacer()
                    
                    Button(action: onAddSet) {
                        Image(systemName: "plus.circle.fill")
                            .foregroundColor(WorkoutDesignSystem.primaryBlue)
                    }
                }
                
                if exercise.sets.isEmpty {
                    Text("No sets configured")
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .padding(.vertical, WorkoutDesignSystem.itemSpacing)
                } else {
                    VStack(spacing: WorkoutDesignSystem.itemSpacing) {
                        ForEach(Array(exercise.sets.enumerated()), id: \.element.id) { index, set in
                            TemplateSetRow(
                                setNumber: index + 1,
                                set: set,
                                exerciseId: exercise.id,
                                onDelete: { onRemoveSet(set.id) }
                            )
                        }
                    }
                }
            }
        }
        .padding(WorkoutDesignSystem.cardPadding)
        .background(Color(.systemBackground))
        .cornerRadius(WorkoutDesignSystem.cardCornerRadius)
        .shadow(radius: 2)
        .onAppear {
            if exercisesViewModel.exercises.isEmpty {
                Task {
                    await exercisesViewModel.loadExercises()
                }
            }
        }
    }
}

// MARK: - Template Set Row (Simple Version)
struct TemplateSetRow: View {
    let setNumber: Int
    let set: WorkoutTemplateSet
    let exerciseId: String
    let onDelete: () -> Void
    @StateObject private var templateManager = TemplateManager.shared
    @State private var showingTypeMenu = false
    
    var body: some View {
        HStack(spacing: 12) {
            // Set number with type
            VStack(spacing: 2) {
                Text("\(setNumber)")
                    .font(WorkoutDesignSystem.setNumberFont)
                
                Button(action: { showingTypeMenu = true }) {
                    Text(setTypeAbbreviation)
                        .font(WorkoutDesignSystem.labelFont)
                        .foregroundColor(.secondary)
                        .padding(.horizontal, 4)
                        .padding(.vertical, 1)
                        .background(Color(.systemGray5))
                        .cornerRadius(3)
                }
            }
            .frame(width: 35)
            
            // Weight input
            VStack(spacing: 2) {
                Text("kg")
                    .font(WorkoutDesignSystem.labelFont)
                    .foregroundColor(.secondary)
                
                WeightInput(
                    value: Binding(
                        get: { set.weight },
                        set: { newWeight in
                            templateManager.updateSetWeight(exerciseId: exerciseId, setId: set.id, weight: newWeight)
                        }
                    ),
                    isDisabled: false
                )
                .frame(width: 60)
            }
            
            // Reps input
            VStack(spacing: 2) {
                Text("reps")
                    .font(WorkoutDesignSystem.labelFont)
                    .foregroundColor(.secondary)
                
                RepsInput(
                    value: Binding(
                        get: { set.reps },
                        set: { newReps in
                            templateManager.updateSetReps(exerciseId: exerciseId, setId: set.id, reps: newReps)
                        }
                    ),
                    isDisabled: false
                )
                .frame(width: 50)
            }
            
            // RIR input (optional for templates)
            VStack(spacing: 2) {
                Text("RIR")
                    .font(WorkoutDesignSystem.labelFont)
                    .foregroundColor(.secondary)
                
                RepsInput(
                    value: Binding(
                        get: { set.rir },
                        set: { newRir in
                            templateManager.updateSetRir(exerciseId: exerciseId, setId: set.id, rir: newRir)
                        }
                    ),
                    isDisabled: false
                )
                .frame(width: 40)
            }
            
            Spacer()
            
            // Delete button
            Button(action: onDelete) {
                Image(systemName: "trash")
                    .foregroundColor(WorkoutDesignSystem.destructiveRed)
                    .font(.caption)
            }
            .frame(width: 30)
        }
        .padding(WorkoutDesignSystem.cardPadding)
        .background(WorkoutDesignSystem.cardBackground)
        .cornerRadius(WorkoutDesignSystem.fieldCornerRadius)
        .sheet(isPresented: $showingTypeMenu) {
            TemplateSetTypeSelector(
                selectedType: Binding(
                    get: { set.type },
                    set: { newType in
                        templateManager.updateSetType(exerciseId: exerciseId, setId: set.id, type: newType)
                    }
                )
            )
        }

    }
    
    private var setTypeAbbreviation: String {
        switch set.type {
        case "Working Set": return "W"
        case "Warm-up": return "WU"
        case "Drop Set": return "D"
        case "Failure Set": return "F"
        default: return "W"
        }
    }
}

// MARK: - Template Set Type Selector (Simplified)
struct TemplateSetTypeSelector: View {
    @Binding var selectedType: String
    @Environment(\.presentationMode) var presentationMode
    
    private let setTypes = ["Working Set", "Warm-up", "Drop Set", "Failure Set"]
    
    var body: some View {
        NavigationView {
            List {
                ForEach(setTypes, id: \.self) { type in
                    Button(action: {
                        selectedType = type
                        presentationMode.wrappedValue.dismiss()
                    }) {
                        HStack {
                            Text(type)
                                .foregroundColor(.primary)
                            Spacer()
                            if selectedType == type {
                                Image(systemName: "checkmark")
                                    .foregroundColor(WorkoutDesignSystem.primaryBlue)
                            }
                        }
                    }
                }
            }
            .navigationTitle("Set Type")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Done") {
                        presentationMode.wrappedValue.dismiss()
                    }
                }
            }
        }
        .presentationDetents([.medium])
    }
}

// MARK: - Template Metadata Form (Simplified - AI will calculate category/difficulty/duration)
struct TemplateMetadataForm: View {
    @Binding var name: String
    @Binding var description: String
    
    var body: some View {
        VStack(alignment: .leading, spacing: WorkoutDesignSystem.sectionSpacing) {
            // Template Name (Required)
            VStack(alignment: .leading, spacing: 4) {
                Text("Template Name *")
                    .font(.subheadline)
                    .fontWeight(.medium)
                
                TextField("Enter a descriptive name", text: $name)
                    .textFieldStyle(RoundedBorderTextFieldStyle())
            }
            
            // Description (Optional)
            VStack(alignment: .leading, spacing: 4) {
                Text("Description")
                    .font(.subheadline)
                    .fontWeight(.medium)
                
                TextField("Describe this workout template", text: $description, axis: .vertical)
                    .textFieldStyle(RoundedBorderTextFieldStyle())
                    .lineLimit(3...6)
            }
            
            // Removed AI Analysis section - streamlining to current functionality
        }
        .padding(WorkoutDesignSystem.cardPadding)
        .background(Color(.systemBackground))
        .cornerRadius(WorkoutDesignSystem.cardCornerRadius)
        .shadow(radius: 2)
    }
}

// MARK: - Template Action Buttons
struct TemplateActionButtons: View {
    let onSave: () -> Void
    let onCancel: () -> Void
    let isSaving: Bool
    let canSave: Bool
    
    var body: some View {
        HStack(spacing: 12) {
            Button(action: onCancel) {
                Text("Cancel")
            }
            .buttonStyle(TemplateSecondaryButtonStyle())
            .disabled(isSaving)
            
            Button(action: onSave) {
                HStack(spacing: 4) {
                    if isSaving {
                        ProgressView()
                            .scaleEffect(0.7)
                        Text("Saving...")
                    } else {
                        Text("Save Template")
                    }
                }
            }
            .buttonStyle(TemplatePrimaryButtonStyle())
            .disabled(isSaving || !canSave)
        }
    }
}

// MARK: - Template Button Styles (Consistent with Active Workout)
struct TemplatePrimaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(.subheadline, weight: .semibold))
            .foregroundColor(.white)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 10)
            .padding(.horizontal, 16)
            .background(
                RoundedRectangle(cornerRadius: WorkoutDesignSystem.buttonCornerRadius)
                    .fill(WorkoutDesignSystem.primaryBlue)
                    .opacity(configuration.isPressed ? 0.8 : 1.0)
            )
    }
}

struct TemplateSecondaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(.subheadline, weight: .medium))
            .foregroundColor(WorkoutDesignSystem.primaryBlue)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 10)
            .padding(.horizontal, 16)
            .background(
                RoundedRectangle(cornerRadius: WorkoutDesignSystem.buttonCornerRadius)
                    .fill(WorkoutDesignSystem.cardBackground)
                    .opacity(configuration.isPressed ? 0.8 : 1.0)
            )
    }
}

// MARK: - Reusable Exercise Components for Templates and Active Workouts

// MARK: - Exercise Selector Component
struct ExerciseSelectorView: View {
    @Binding var selectedExercises: [String: Exercise] // exerciseId -> Exercise
    let onAddExercise: () -> Void
    @State private var showingSelection = false
    
    var body: some View {
        VStack(spacing: 12) {
            HStack {
                Text("Exercises")
                    .font(.headline)
                Spacer()
                Button(action: { showingSelection = true }) {
                    Label("Add Exercise", systemImage: "plus")
                }
            }
            
            if selectedExercises.isEmpty {
                EmptyExerciseState(onAddExercise: { showingSelection = true })
            } else {
                Text("\(selectedExercises.count) exercise(s) selected")
                    .font(.subheadline)
                    .foregroundColor(.secondary)
            }
        }
        .sheet(isPresented: $showingSelection) {
            ExerciseSelectionView { exercise in
                selectedExercises[exercise.id] = exercise
                onAddExercise()
                showingSelection = false
            }
        }
    }
}

// MARK: - Reorderable Exercise List
struct ReorderableExerciseList<T: ExerciseRepresentable>: View {
    @Binding var exercises: [T]
    let onReorder: (IndexSet, Int) -> Void
    let onDelete: (IndexSet) -> Void
    let exerciseRowContent: (T) -> AnyView
    
    var body: some View {
        List {
            ForEach(exercises) { exercise in
                HStack {
                    // Drag handle
                    Image(systemName: "line.3.horizontal")
                        .foregroundColor(.gray)
                    
                    exerciseRowContent(exercise)
                }
            }
            .onMove(perform: onReorder)
            .onDelete(perform: onDelete)
        }
        .environment(\.editMode, .constant(EditMode.active))
    }
}

// MARK: - Set Configuration Component
struct SetConfigurationView: View {
    @Binding var sets: [ConfigurableSet]
    let isTemplate: Bool
    let exerciseId: String
    let onAddSet: () -> Void
    let onUpdateSet: (ConfigurableSet) -> Void
    let onDeleteSet: (String) -> Void
    
    var body: some View {
        VStack(spacing: 12) {
            // Header
            HStack {
                Text("Sets")
                    .font(.subheadline)
                    .fontWeight(.medium)
                
                Spacer()
                
                Button(action: onAddSet) {
                    Image(systemName: "plus.circle.fill")
                        .foregroundColor(.blue)
                }
            }
            
            if sets.isEmpty {
                Text("No sets configured")
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .padding(.vertical, 8)
            } else {
                VStack(spacing: 8) {
                    // Header row
                    SetHeaderRow(isTemplate: isTemplate)
                    
                    // Set rows
                    ForEach(Array(sets.enumerated()), id: \.element.id) { index, set in
                        ConfigurableSetRow(
                            setNumber: index + 1,
                            set: Binding(
                                get: { set },
                                set: { newSet in
                                    sets[index] = newSet
                                    onUpdateSet(newSet)
                                }
                            ),
                            isTemplate: isTemplate,
                            onDelete: { onDeleteSet(set.id) }
                        )
                    }
                }
            }
        }
        .padding()
        .background(Color(.systemGray6))
        .cornerRadius(12)
    }
}

// MARK: - Set Header Row
struct SetHeaderRow: View {
    @StateObject private var userService = UserService.shared
    let isTemplate: Bool
    
    init(isTemplate: Bool = false) {
        self.isTemplate = isTemplate
    }
    
    var body: some View {
        HStack {
            Text("Set")
                .font(.caption)
                .foregroundColor(.secondary)
                .frame(width: 30, alignment: .leading)
            
            Text("Weight (\(userService.weightUnit))")
                .font(.caption)
                .foregroundColor(.secondary)
                .frame(width: 70, alignment: .center)
            
            Text("Reps")
                .font(.caption)
                .foregroundColor(.secondary)
                .frame(width: 50, alignment: .center)
            
            if !isTemplate {
                Text("RIR")
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .frame(width: 40, alignment: .center)
            }
            
            Text("Type")
                .font(.caption)
                .foregroundColor(.secondary)
                .frame(maxWidth: .infinity, alignment: .leading)
            
            if !isTemplate {
                Text("✓") // Completion column
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .frame(width: 25, alignment: .center)
            }
            
            Text("") // Delete button space
                .frame(width: 30)
        }
    }
}

// MARK: - Configurable Set Row
struct ConfigurableSetRow: View {
    let setNumber: Int
    @Binding var set: ConfigurableSet
    let isTemplate: Bool
    let onDelete: () -> Void
    
    var body: some View {
        HStack(spacing: 8) {
            Text("\(setNumber)")
                .font(.subheadline)
                .fontWeight(.medium)
                .frame(width: 30, alignment: .leading)
                .opacity(isTemplate || !set.isCompleted ? 1.0 : 0.6)
            
            // Weight input
            WeightInput(value: $set.weight, isDisabled: !isTemplate && set.isCompleted)
            
            // Reps input  
            RepsInput(value: $set.reps, isDisabled: !isTemplate && set.isCompleted)
            
            // RIR input (hidden for templates if not wanted)
            if !isTemplate {
                TextField("0", value: $set.rir, format: .number)
                    .textFieldStyle(RoundedBorderTextFieldStyle())
                    .frame(width: 40)
                    .keyboardType(.numberPad)
                    .opacity(!set.isCompleted ? 1.0 : 0.6)
                    .disabled(set.isCompleted)
            } else {
                // Placeholder for template
                Text("-")
                    .frame(width: 40)
                    .foregroundColor(.secondary)
            }
            
            // Type picker
            Menu(set.type) {
                ForEach(SetType.allCases, id: \.self) { type in
                    Button(type.displayName) { 
                        set.type = type.rawValue
                    }
                }
            }
            .font(.caption)
            .frame(maxWidth: .infinity, alignment: .leading)
            .opacity(isTemplate || !set.isCompleted ? 1.0 : 0.6)
            .disabled(!isTemplate && set.isCompleted)
            
            // Completion checkbox (only for active workouts)
            if !isTemplate {
                Button(action: {
                    toggleCompletion()
                }) {
                    Image(systemName: set.isCompleted ? "checkmark.circle.fill" : "circle")
                        .font(.title3)
                        .foregroundColor(set.isCompleted ? .green : .gray)
                        .animation(.easeInOut(duration: 0.2), value: set.isCompleted)
                }
                .buttonStyle(PlainButtonStyle())
                .frame(width: 25)
            }
            
            // Delete button
            Button(action: onDelete) {
                Image(systemName: "trash")
                    .foregroundColor(.red)
                    .font(.caption)
            }
            .frame(width: 30)
            .opacity(isTemplate || !set.isCompleted ? 1.0 : 0.4)
        }
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(!isTemplate && set.isCompleted ? Color.green.opacity(0.1) : Color.clear)
        )
        .animation(.easeInOut(duration: 0.2), value: set.isCompleted)
    }
    
    private func toggleCompletion() {
        // Haptic feedback
        let impactFeedback = UIImpactFeedbackGenerator(style: .medium)
        impactFeedback.impactOccurred()
        
        set.isCompleted.toggle()
    }
}

// MARK: - Empty Exercise State
private struct EmptyExerciseState: View {
    let onAddExercise: () -> Void
    
    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: "dumbbell")
                .font(.system(size: 40))
                .foregroundColor(.gray)
            
            Text("No exercises selected")
                .font(.subheadline)
                .foregroundColor(.secondary)
            
            Button(action: onAddExercise) {
                Label("Add Exercise", systemImage: "plus")
                    .padding(.horizontal, 16)
                    .padding(.vertical, 8)
                    .background(Color.blue)
                    .foregroundColor(.white)
                    .cornerRadius(8)
            }
        }
        .padding()
        .frame(maxWidth: .infinity)
        .background(Color(.systemGray6))
        .cornerRadius(12)
    }
}

// MARK: - Supporting Types and Protocols

protocol ExerciseRepresentable: Identifiable {
    var id: String { get }
    var name: String { get }
    var position: Int { get set }
}

extension ActiveExercise: ExerciseRepresentable {}

struct ConfigurableSet: Identifiable, Equatable {
    let id: String
    var reps: Int
    var rir: Int
    var weight: Double
    var type: String
    var isCompleted: Bool = false
    
    // Convert from ActiveSet
    init(from activeSet: ActiveSet) {
        self.id = activeSet.id
        self.reps = activeSet.reps
        self.rir = activeSet.rir
        self.weight = activeSet.weight
        self.type = activeSet.type
        self.isCompleted = activeSet.isCompleted
    }
    
    // Convert from WorkoutTemplateSet
    init(from templateSet: WorkoutTemplateSet) {
        self.id = templateSet.id
        self.reps = templateSet.reps
        self.rir = templateSet.rir
        self.weight = templateSet.weight
        self.type = templateSet.type
        self.isCompleted = false
    }
    
    // Create new
    init(id: String = UUID().uuidString, reps: Int = 0, rir: Int = 0, weight: Double = 0.0, type: String = "Working Set") {
        self.id = id
        self.reps = reps
        self.rir = rir
        self.weight = weight
        self.type = type
        self.isCompleted = false
    }
    
    // Convert to ActiveSet
    func toActiveSet() -> ActiveSet {
        return ActiveSet(
            id: id,
            reps: reps,
            rir: rir,
            type: type,
            weight: weight,
            isCompleted: isCompleted
        )
    }
    
    // Convert to WorkoutTemplateSet
    func toTemplateSet() -> WorkoutTemplateSet {
        return WorkoutTemplateSet(
            id: id,
            reps: reps,
            rir: rir,
            type: type,
            weight: weight,
            duration: nil
        )
    }
}

enum SetType: String, CaseIterable {
    case warmup = "Warm-up"
    case workingSet = "Working Set"
    case dropSet = "Drop Set"
    case failureSet = "Failure Set"
    
    var displayName: String {
        return rawValue
    }
}

// MARK: - Simple Exercise List for Templates
struct SimpleExerciseList<T: ExerciseRepresentable>: View {
    @Binding var exercises: [T]
    let exerciseContent: (T) -> AnyView
    
    var body: some View {
        LazyVStack(spacing: 12) {
            ForEach(exercises) { exercise in
                exerciseContent(exercise)
            }
        }
    }
}

// MARK: - Muscle Stimulus Projection Visualization
struct MuscleStimulusProjection: View {
    let analytics: TemplateAnalytics
    @State private var selectedView: StimulusView = .muscleGroups
    
    enum StimulusView: String, CaseIterable {
        case muscleGroups = "Groups"
        case individualMuscles = "Muscles"
    }
    
    var body: some View {
        VStack(alignment: .leading, spacing: WorkoutDesignSystem.sectionSpacing) {
            // Header with toggle
            HStack {
                Text("Muscle Stimulus Projection")
                    .font(.headline)
                    .fontWeight(.semibold)
                
                Spacer()
                
                Picker("View", selection: $selectedView) {
                    ForEach(StimulusView.allCases, id: \.self) { view in
                        Text(view.rawValue).tag(view)
                    }
                }
                .pickerStyle(SegmentedPickerStyle())
                .frame(width: 150)
            }
            
            // Stimulus visualization
            switch selectedView {
            case .muscleGroups:
                MuscleGroupStimulusChart(
                    volumePerMuscleGroup: analytics.projectedVolumePerMuscleGroup,
                    setsPerMuscleGroup: analytics.setsPerMuscleGroup,
                    weightFormat: analytics.weightFormat
                )
            case .individualMuscles:
                IndividualMuscleStimulusChart(
                    volumePerMuscle: analytics.projectedVolumePerMuscle,
                    setsPerMuscle: analytics.setsPerMuscle,
                    weightFormat: analytics.weightFormat
                )
            }
            
            // Summary stats
            StimulusSummaryStats(analytics: analytics)
        }
        .padding(WorkoutDesignSystem.cardPadding)
        .background(Color(.systemBackground))
        .cornerRadius(WorkoutDesignSystem.cardCornerRadius)
        .shadow(radius: 2)
    }
}

// MARK: - Muscle Group Stimulus Chart
struct MuscleGroupStimulusChart: View {
    let volumePerMuscleGroup: [String: Double]
    let setsPerMuscleGroup: [String: Int]
    let weightFormat: String
    
    private var sortedMuscleGroups: [(group: String, volume: Double, sets: Int)] {
        volumePerMuscleGroup
            .map { (group: $0.key, volume: $0.value, sets: setsPerMuscleGroup[$0.key] ?? 0) }
            .sorted { $0.volume > $1.volume }
    }
    
    private var maxVolume: Double {
        volumePerMuscleGroup.values.max() ?? 1.0
    }
    
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if sortedMuscleGroups.isEmpty {
                Text("Add exercises to see muscle stimulus projection")
                    .font(.subheadline)
                    .foregroundColor(.secondary)
                    .frame(maxWidth: .infinity, alignment: .center)
                    .padding(.vertical, 20)
            } else {
                ForEach(sortedMuscleGroups, id: \.group) { data in
                    MuscleGroupStimulusBar(
                        group: data.group,
                        volume: data.volume,
                        sets: data.sets,
                        maxVolume: maxVolume,
                        weightFormat: weightFormat
                    )
                }
            }
        }
    }
}

// MARK: - Individual Muscle Stimulus Chart
struct IndividualMuscleStimulusChart: View {
    let volumePerMuscle: [String: Double]
    let setsPerMuscle: [String: Int]
    let weightFormat: String
    
    private var sortedMuscles: [(muscle: String, volume: Double, sets: Int)] {
        volumePerMuscle
            .map { (muscle: $0.key, volume: $0.value, sets: setsPerMuscle[$0.key] ?? 0) }
            .sorted { $0.volume > $1.volume }
            .prefix(10) // Show top 10 muscles to avoid clutter
            .map { $0 }
    }
    
    private var maxVolume: Double {
        volumePerMuscle.values.max() ?? 1.0
    }
    
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if sortedMuscles.isEmpty {
                Text("Add exercises to see individual muscle targeting")
                    .font(.subheadline)
                    .foregroundColor(.secondary)
                    .frame(maxWidth: .infinity, alignment: .center)
                    .padding(.vertical, 20)
            } else {
                ForEach(sortedMuscles, id: \.muscle) { data in
                    IndividualMuscleStimulusBar(
                        muscle: data.muscle,
                        volume: data.volume,
                        sets: data.sets,
                        maxVolume: maxVolume,
                        weightFormat: weightFormat
                    )
                }
                
                if volumePerMuscle.count > 10 {
                    Text("Showing top 10 muscles by volume")
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .padding(.top, 8)
                }
            }
        }
    }
}

// MARK: - Muscle Group Stimulus Bar
struct MuscleGroupStimulusBar: View {
    let group: String
    let volume: Double
    let sets: Int
    let maxVolume: Double
    let weightFormat: String
    
    private var fillRatio: Double {
        maxVolume > 0 ? volume / maxVolume : 0
    }
    
    private var muscleGroupColor: Color {
        switch group.lowercased() {
        case "chest": return .red
        case "back": return .green
        case "shoulders": return .orange
        case "biceps": return .blue
        case "triceps": return .purple
        case "quadriceps": return .yellow
        case "hamstrings": return .brown
        case "glutes": return .pink
        case "calves": return .gray
        default: return .primary
        }
    }
    
    var body: some View {
        VStack(spacing: 4) {
            HStack {
                Text(group.capitalized)
                    .font(.subheadline)
                    .fontWeight(.medium)
                    .frame(width: 80, alignment: .leading)
                
                // Progress bar
                ZStack(alignment: .leading) {
                    Rectangle()
                        .fill(Color(.systemGray5))
                        .frame(height: 20)
                        .cornerRadius(4)
                    
                    Rectangle()
                        .fill(muscleGroupColor.opacity(0.8))
                        .frame(width: max(2, fillRatio * 200), height: 20)
                        .cornerRadius(4)
                        .animation(.easeInOut(duration: 0.3), value: fillRatio)
                }
                .frame(width: 200)
                
                Spacer()
                
                VStack(alignment: .trailing, spacing: 2) {
                    Text("\(String(format: "%.0f", volume))\(weightFormat)")
                        .font(.subheadline)
                        .fontWeight(.semibold)
                        .foregroundColor(muscleGroupColor)
                    
                    Text("\(sets) sets")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                .frame(width: 60)
            }
        }
    }
}

// MARK: - Individual Muscle Stimulus Bar
struct IndividualMuscleStimulusBar: View {
    let muscle: String
    let volume: Double
    let sets: Int
    let maxVolume: Double
    let weightFormat: String
    
    private var fillRatio: Double {
        maxVolume > 0 ? volume / maxVolume : 0
    }
    
    var body: some View {
        VStack(spacing: 4) {
            HStack {
                Text(muscle.capitalized)
                    .font(.caption)
                    .frame(width: 100, alignment: .leading)
                
                // Progress bar (smaller for individual muscles)
                ZStack(alignment: .leading) {
                    Rectangle()
                        .fill(Color(.systemGray5))
                        .frame(height: 12)
                        .cornerRadius(2)
                    
                    Rectangle()
                        .fill(WorkoutDesignSystem.primaryBlue.opacity(0.7))
                        .frame(width: max(1, fillRatio * 150), height: 12)
                        .cornerRadius(2)
                        .animation(.easeInOut(duration: 0.3), value: fillRatio)
                }
                .frame(width: 150)
                
                Spacer()
                
                Text("\(String(format: "%.0f", volume))\(weightFormat)")
                    .font(.caption)
                    .fontWeight(.medium)
                    .frame(width: 50, alignment: .trailing)
            }
        }
    }
}

// MARK: - Stimulus Summary Stats
struct StimulusSummaryStats: View {
    let analytics: TemplateAnalytics
    
    var body: some View {
        VStack(spacing: 12) {
            Divider()
            
            HStack {
                Text("Template Summary")
                    .font(.subheadline)
                    .fontWeight(.semibold)
                    .foregroundColor(.secondary)
                
                Spacer()
            }
            
            HStack(spacing: 20) {
                SummaryStatItem(
                    title: "Total Sets",
                    value: "\(analytics.totalSets)",
                    color: .blue
                )
                
                SummaryStatItem(
                    title: "Total Volume",
                    value: "\(String(format: "%.0f", analytics.projectedVolume))\(analytics.weightFormat)",
                    color: .green
                )
                
                if let duration = analytics.estimatedDuration {
                    SummaryStatItem(
                        title: "Est. Duration",
                        value: "\(duration)min",
                        color: .orange
                    )
                }
                
                Spacer()
            }
        }
    }
}

// MARK: - Specialized Input Components (Fix for Input Bug)

struct WeightInput: View {
    @Binding var value: Double
    let isDisabled: Bool
    @State private var textValue: String = ""
    @State private var isInitialized = false
    
    var body: some View {
        TextField("0", text: $textValue)
            .textFieldStyle(RoundedBorderTextFieldStyle())
            .frame(width: 70)
            .keyboardType(.decimalPad)
            .opacity(isDisabled ? 0.6 : 1.0)
            .disabled(isDisabled)
            .onChange(of: textValue) { oldValue, newValue in
                // Update the binding value when user types
                if let doubleValue = Double(newValue), doubleValue >= 0 {
                    value = doubleValue
                } else if newValue.isEmpty {
                    value = 0
                }
            }
            .onAppear {
                // Initialize text value once
                if !isInitialized {
                    if value == 0 {
                        textValue = ""
                    } else {
                        textValue = String(format: "%.1f", value).replacingOccurrences(of: ".0", with: "")
                    }
                    isInitialized = true
                }
            }

    }
}

struct RepsInput: View {
    @Binding var value: Int
    let isDisabled: Bool
    @State private var textValue: String = ""
    @State private var isInitialized = false
    
    var body: some View {
        TextField("0", text: $textValue)
            .textFieldStyle(RoundedBorderTextFieldStyle())
            .frame(width: 50)
            .keyboardType(.numberPad)
            .opacity(isDisabled ? 0.6 : 1.0)
            .disabled(isDisabled)
            .onChange(of: textValue) { oldValue, newValue in
                // Update the binding value when user types
                if let intValue = Int(newValue), intValue >= 0 {
                    value = intValue
                } else if newValue.isEmpty {
                    value = 0
                }
            }
            .onAppear {
                // Initialize text value once
                if !isInitialized {
                    if value == 0 {
                        textValue = ""
                    } else {
                        textValue = "\(value)"
                    }
                    isInitialized = true
                }
            }

    }
}

struct SummaryStatItem: View {
    let title: String
    let value: String
    let color: Color
    
    var body: some View {
        VStack(spacing: 2) {
            Text(value)
                .font(.headline)
                .fontWeight(.bold)
                .foregroundColor(color)
            
            Text(title)
                .font(.caption)
                .foregroundColor(.secondary)
        }
    }
}

// MARK: - Real-time Template Analytics Calculator
struct TemplateAnalyticsCalculator: View {
    @Binding var template: WorkoutTemplate
    @State private var analytics: TemplateAnalytics?
    @StateObject private var exercisesViewModel = ExercisesViewModel()
    
    var body: some View {
        Group {
            if let analytics = analytics {
                MuscleStimulusProjection(analytics: analytics)
            } else {
                VStack(spacing: 16) {
                    ProgressView("Calculating stimulus projection...")
                        .frame(maxWidth: .infinity, alignment: .center)
                        .padding(.vertical, 40)
                }
                .padding(WorkoutDesignSystem.cardPadding)
                .background(Color(.systemBackground))
                .cornerRadius(WorkoutDesignSystem.cardCornerRadius)
                .shadow(radius: 2)
            }
        }
        .onAppear {
            loadExercisesAndCalculate()
        }
        .onChange(of: template.exercises) { oldValue, newValue in
            calculateAnalytics()
        }
        .onChange(of: template.exercises.map(\.sets)) { oldValue, newValue in
            calculateAnalytics()
        }
    }
    
    private func loadExercisesAndCalculate() {
        Task {
            if exercisesViewModel.exercises.isEmpty {
                await exercisesViewModel.loadExercises()
            }
            await MainActor.run {
                calculateAnalytics()
            }
        }
    }
    
    private func calculateAnalytics() {
        analytics = StimulusCalculator.calculateTemplateAnalytics(
            template: template,
            exercises: exercisesViewModel.exercises
        )
    }
}

// MARK: - Template Balance Guidance
struct TemplateBalanceGuidance: View {
    let analytics: TemplateAnalytics
    
    private var balanceInsights: [BalanceInsight] {
        var insights: [BalanceInsight] = []
        
        // Check for muscle group imbalances
        let muscleGroups = analytics.projectedVolumePerMuscleGroup
        
        let pushVolume = (muscleGroups["chest"] ?? 0) + (muscleGroups["shoulders"] ?? 0) + (muscleGroups["triceps"] ?? 0)
        let pullVolume = (muscleGroups["back"] ?? 0) + (muscleGroups["biceps"] ?? 0)
        
        if pushVolume > 0 && pullVolume > 0 {
            let ratio = pushVolume / pullVolume
            if ratio > 1.5 {
                insights.append(BalanceInsight(
                    type: .warning,
                    title: "Push/Pull Imbalance",
                    description: "This template is push-heavy (\(String(format: "%.1f", ratio)):1 ratio). Consider adding more pulling exercises.",
                    suggestion: "Add rowing, pull-ups, or face pulls"
                ))
            } else if ratio < 0.67 {
                insights.append(BalanceInsight(
                    type: .warning,
                    title: "Push/Pull Imbalance",
                    description: "This template is pull-heavy (\(String(format: "%.1f", ratio)):1 ratio). Consider adding more pushing exercises.",
                    suggestion: "Add push-ups, overhead press, or chest press"
                ))
            } else {
                insights.append(BalanceInsight(
                    type: .success,
                    title: "Balanced Push/Pull",
                    description: "Good push/pull balance (\(String(format: "%.1f", ratio)):1 ratio)",
                    suggestion: nil
                ))
            }
        }
        
        // Check total volume
        if analytics.projectedVolume < 2000 {
            insights.append(BalanceInsight(
                type: .info,
                title: "Low Volume Template",
                description: "This appears to be a low-volume workout. Great for beginners or deload weeks.",
                suggestion: nil
            ))
        } else if analytics.projectedVolume > 8000 {
            insights.append(BalanceInsight(
                type: .warning,
                title: "High Volume Template",
                description: "This is a high-volume workout. Ensure adequate recovery between sessions.",
                suggestion: "Consider splitting into multiple sessions"
            ))
        }
        
        return insights
    }
    
    var body: some View {
        if !balanceInsights.isEmpty {
            VStack(alignment: .leading, spacing: 12) {
                Text("Balance Analysis")
                    .font(.headline)
                    .fontWeight(.semibold)
                
                ForEach(balanceInsights.indices, id: \.self) { index in
                    BalanceInsightCard(insight: balanceInsights[index])
                }
            }
            .padding(WorkoutDesignSystem.cardPadding)
            .background(Color(.systemBackground))
            .cornerRadius(WorkoutDesignSystem.cardCornerRadius)
            .shadow(radius: 2)
        }
    }
}

struct BalanceInsight {
    let type: InsightType
    let title: String
    let description: String
    let suggestion: String?
    
    enum InsightType {
        case success, warning, info
        
        var color: Color {
            switch self {
            case .success: return .green
            case .warning: return .orange
            case .info: return .blue
            }
        }
        
        var icon: String {
            switch self {
            case .success: return "checkmark.circle"
            case .warning: return "exclamationmark.triangle"
            case .info: return "info.circle"
            }
        }
    }
}

struct BalanceInsightCard: View {
    let insight: BalanceInsight
    
    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: insight.type.icon)
                .foregroundColor(insight.type.color)
                .font(.title3)
                .frame(width: 20)
            
            VStack(alignment: .leading, spacing: 4) {
                Text(insight.title)
                    .font(.subheadline)
                    .fontWeight(.semibold)
                    .foregroundColor(insight.type.color)
                
                Text(insight.description)
                    .font(.caption)
                    .foregroundColor(.primary)
                
                if let suggestion = insight.suggestion {
                    Text("💡 \(suggestion)")
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .italic()
                }
            }
            
            Spacer()
        }
        .padding(12)
        .background(insight.type.color.opacity(0.1))
        .cornerRadius(8)
    }
} 