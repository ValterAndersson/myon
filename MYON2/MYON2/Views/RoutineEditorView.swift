import SwiftUI

struct RoutineEditorView: View {
    @State private var routine: Routine
    @State private var availableTemplates: [WorkoutTemplate] = []
    @State private var selectedTemplates: [WorkoutTemplate] = []
    @State private var routineAnalytics: RoutineAnalytics?
    @State private var showingTemplateSelection = false
    @State private var isSaving = false
    @StateObject private var exercisesViewModel = ExercisesViewModel()
    @Environment(\.presentationMode) var presentationMode
    
    let onSave: (Routine) -> Void
    let isEditing: Bool
    
    // Initialize for creating new routine
    init(onSave: @escaping (Routine) -> Void) {
        self.onSave = onSave
        self.isEditing = false
        self._routine = State(initialValue: Routine(
            id: UUID().uuidString,
            userId: "", // Will be set by the service
            name: "",
            description: "",
            templateIds: [],
            frequency: 3,
            createdAt: Date(),
            updatedAt: Date()
        ))
    }
    
    // Initialize for editing existing routine
    init(routine: Routine, onSave: @escaping (Routine) -> Void) {
        self.onSave = onSave
        self.isEditing = true
        self._routine = State(initialValue: routine)
    }
    
    var body: some View {
        NavigationView {
            ScrollView {
                VStack(spacing: 24) {
                    // Routine Metadata
                    RoutineMetadataForm(routine: $routine)
                    
                    // Weekly Analytics (if templates are selected)
                    if !selectedTemplates.isEmpty, let analytics = routineAnalytics {
                        WeeklyRoutineAnalytics(analytics: analytics)
                            .padding(.horizontal)
                    }
                    
                    // Template Management
                    TemplateManagementSection(
                        selectedTemplates: $selectedTemplates,
                        onAddTemplate: { showingTemplateSelection = true },
                        onRemoveTemplate: removeTemplate,
                        onReorderTemplates: reorderTemplates
                    )
                    .padding(.horizontal)
                    
                    // Action Buttons
                    RoutineActionButtons(
                        onSave: saveRoutine,
                        onCancel: { presentationMode.wrappedValue.dismiss() },
                        isSaving: isSaving,
                        canSave: canSaveRoutine
                    )
                    .padding(.horizontal)
                    .padding(.bottom, 40)
                }
            }
            .navigationTitle(isEditing ? "Edit Routine" : "New Routine")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Cancel") {
                        presentationMode.wrappedValue.dismiss()
                    }
                    .disabled(isSaving)
                }
            }
        }
        .sheet(isPresented: $showingTemplateSelection) {
            TemplateSelectionSheet(
                availableTemplates: availableTemplates,
                selectedTemplateIds: Set(routine.templateIds),
                onTemplateSelected: addTemplate
            )
        }
        .onAppear {
            loadTemplatesAndCalculate()
        }
        .onChange(of: selectedTemplates) { oldValue, newValue in
            updateRoutineAnalytics()
        }
        .onChange(of: routine.frequency) { oldValue, newValue in
            updateRoutineAnalytics()
        }
    }
    
    // MARK: - Data Management
    
    private func loadTemplatesAndCalculate() {
        Task {
            if exercisesViewModel.exercises.isEmpty {
                await exercisesViewModel.loadExercises()
            }

            // Fetch templates for the current user
            if let userId = AuthService.shared.currentUser?.uid {
                do {
                    let templates = try await TemplateRepository().getTemplates(userId: userId)
                    await MainActor.run {
                        self.availableTemplates = templates
                        updateSelectedTemplates()
                        updateRoutineAnalytics()
                    }
                } catch {
                    print("Error loading templates: \(error)")
                    await MainActor.run {
                        self.availableTemplates = []
                        updateSelectedTemplates()
                        updateRoutineAnalytics()
                    }
                }
            } else {
                await MainActor.run {
                    self.availableTemplates = []
                    updateSelectedTemplates()
                    updateRoutineAnalytics()
                }
            }
        }
    }
    
    private func updateSelectedTemplates() {
        // TODO: Fetch templates by IDs from repository
        // For now, keep existing selected templates
    }
    
    private func updateRoutineAnalytics() {
        guard !selectedTemplates.isEmpty else {
            routineAnalytics = nil
            return
        }
        
        // Calculate analytics for each template
        let templateAnalytics = selectedTemplates.map { template in
            StimulusCalculator.calculateTemplateAnalytics(
                template: template,
                exercises: exercisesViewModel.exercises
            )
        }
        
        // Calculate routine-level analytics
        routineAnalytics = StimulusCalculator.calculateRoutineAnalytics(
            routine: routine,
            templateAnalytics: templateAnalytics
        )
    }
    
    // MARK: - Template Management
    
    private func addTemplate(_ template: WorkoutTemplate) {
        if !routine.templateIds.contains(template.id) {
            routine.templateIds.append(template.id)
            selectedTemplates.append(template)
            updateRoutineAnalytics()
        }
    }
    
    private func removeTemplate(_ template: WorkoutTemplate) {
        routine.templateIds.removeAll { $0 == template.id }
        selectedTemplates.removeAll { $0.id == template.id }
        updateRoutineAnalytics()
    }
    
    private func reorderTemplates(fromOffsets: IndexSet, toOffset: Int) {
        selectedTemplates.move(fromOffsets: fromOffsets, toOffset: toOffset)
        routine.templateIds = selectedTemplates.map(\.id)
        updateRoutineAnalytics()
    }
    
    // MARK: - Save Logic
    
    private var canSaveRoutine: Bool {
        !routine.name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty &&
        !routine.templateIds.isEmpty &&
        routine.frequency > 0
    }
    
    private func saveRoutine() {
        guard canSaveRoutine else { return }
        
        isSaving = true
        
        routine.updatedAt = Date()
        
        Task {
            do {
                // Ensure userId is set
                guard let userId = AuthService.shared.currentUser?.uid else {
                    await MainActor.run {
                        print("No authenticated user found")
                        isSaving = false
                    }
                    return
                }
                
                // Create routine with userId if not already set (for new routines)
                let routineToSave = routine.userId.isEmpty ? Routine(
                    id: routine.id,
                    userId: userId,
                    name: routine.name,
                    description: routine.description,
                    templateIds: routine.templateIds,
                    frequency: routine.frequency,
                    createdAt: Date(),
                    updatedAt: routine.updatedAt
                ) : routine
                
                let repository = RoutineRepository()
                
                if isEditing {
                    // Update existing routine
                    try await repository.updateRoutine(routineToSave)
                } else {
                    // Create new routine
                    let _ = try await repository.createRoutine(routineToSave)
                }
                
                await MainActor.run {
                    onSave(routineToSave)
                    isSaving = false
                    presentationMode.wrappedValue.dismiss()
                }
            } catch {
                await MainActor.run {
                    print("Error saving routine: \(error)")
                    isSaving = false
                }
            }
        }
    }
}

// MARK: - Routine Metadata Form
struct RoutineMetadataForm: View {
    @Binding var routine: Routine
    
    // Categories and difficulties will be calculated by AI
    
    var body: some View {
        VStack(alignment: .leading, spacing: WorkoutDesignSystem.sectionSpacing) {
            Text("Routine Information")
                .font(.headline)
                .fontWeight(.semibold)
            
            VStack(alignment: .leading, spacing: 16) {
                // Routine Name (Required)
                VStack(alignment: .leading, spacing: 4) {
                    Text("Routine Name *")
                        .font(.subheadline)
                        .fontWeight(.medium)
                    
                    TextField("e.g., Push/Pull/Legs", text: $routine.name)
                        .textFieldStyle(RoundedBorderTextFieldStyle())
                }
                
                // Description (Optional)
                VStack(alignment: .leading, spacing: 4) {
                    Text("Description")
                        .font(.subheadline)
                        .fontWeight(.medium)
                    
                    TextField("Describe your weekly routine", text: Binding(
                        get: { routine.description ?? "" },
                        set: { routine.description = $0.isEmpty ? nil : $0 }
                    ), axis: .vertical)
                    .textFieldStyle(RoundedBorderTextFieldStyle())
                    .lineLimit(3...6)
                }
                
                // Frequency
                VStack(alignment: .leading, spacing: 4) {
                    Text("Weekly Frequency *")
                        .font(.subheadline)
                        .fontWeight(.medium)
                    
                    HStack {
                        Stepper("", value: $routine.frequency, in: 1...7)
                            .labelsHidden()
                        
                        Text("\(routine.frequency) workout\(routine.frequency == 1 ? "" : "s") per week")
                            .font(.subheadline)
                        
                        Spacer()
                    }
                }
                
                // Category and difficulty will be calculated by AI
            }
        }
        .padding(WorkoutDesignSystem.cardPadding)
        .background(Color(.systemBackground))
        .cornerRadius(WorkoutDesignSystem.cardCornerRadius)
        .shadow(radius: 2)
    }
}

// MARK: - Weekly Routine Analytics
struct WeeklyRoutineAnalytics: View {
    let analytics: RoutineAnalytics
    @State private var selectedMetric: AnalyticsMetric = .volume
    
    enum AnalyticsMetric: String, CaseIterable {
        case volume = "Volume"
        case sets = "Sets"
        case balance = "Balance"
    }
    
    var body: some View {
        VStack(alignment: .leading, spacing: WorkoutDesignSystem.sectionSpacing) {
            // Header
            HStack {
                Text("Weekly Analysis")
                    .font(.headline)
                    .fontWeight(.semibold)
                
                Spacer()
                
                Picker("Metric", selection: $selectedMetric) {
                    ForEach(AnalyticsMetric.allCases, id: \.self) { metric in
                        Text(metric.rawValue).tag(metric)
                    }
                }
                .pickerStyle(SegmentedPickerStyle())
                .frame(width: 200)
            }
            
            // Analytics content
            switch selectedMetric {
            case .volume:
                WeeklyVolumeBreakdown(analytics: analytics)
            case .sets:
                WeeklySetsBreakdown(analytics: analytics)
            case .balance:
                WeeklyBalanceAnalysis(analytics: analytics)
            }
            
            // Quick stats
            WeeklyQuickStats(analytics: analytics)
        }
        .padding(WorkoutDesignSystem.cardPadding)
        .background(Color(.systemBackground))
        .cornerRadius(WorkoutDesignSystem.cardCornerRadius)
        .shadow(radius: 2)
    }
}

struct WeeklyVolumeBreakdown: View {
    let analytics: RoutineAnalytics
    
    private var sortedMuscleGroups: [(group: String, volume: Double)] {
        analytics.weeklyVolumePerMuscleGroup
            .map { (group: $0.key, volume: $0.value) }
            .sorted { $0.volume > $1.volume }
    }
    
    private var maxVolume: Double {
        analytics.weeklyVolumePerMuscleGroup.values.max() ?? 1.0
    }
    
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Weekly Volume by Muscle Group")
                .font(.subheadline)
                .fontWeight(.semibold)
                .foregroundColor(.secondary)
            
            ForEach(sortedMuscleGroups, id: \.group) { data in
                WeeklyMuscleBar(
                    muscle: data.group,
                    value: data.volume,
                    maxValue: maxVolume,
                    format: "\(String(format: "%.0f", data.volume))\(analytics.weightFormat)",
                    color: muscleGroupColor(data.group)
                )
            }
        }
    }
    
    private func muscleGroupColor(_ group: String) -> Color {
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
}

struct WeeklySetsBreakdown: View {
    let analytics: RoutineAnalytics
    
    private var sortedMuscleGroups: [(group: String, sets: Int)] {
        analytics.weeklySetsPerMuscleGroup
            .map { (group: $0.key, sets: $0.value) }
            .sorted { $0.sets > $1.sets }
    }
    
    private var maxSets: Int {
        analytics.weeklySetsPerMuscleGroup.values.max() ?? 1
    }
    
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Weekly Sets by Muscle Group")
                .font(.subheadline)
                .fontWeight(.semibold)
                .foregroundColor(.secondary)
            
            ForEach(sortedMuscleGroups, id: \.group) { data in
                WeeklyMuscleBar(
                    muscle: data.group,
                    value: Double(data.sets),
                    maxValue: Double(maxSets),
                    format: "\(data.sets) sets",
                    color: .blue
                )
            }
        }
    }
}

struct WeeklyBalanceAnalysis: View {
    let analytics: RoutineAnalytics
    
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Muscle Balance Analysis")
                .font(.subheadline)
                .fontWeight(.semibold)
                .foregroundColor(.secondary)
            
            // Balance ratios
            VStack(spacing: 12) {
                BalanceRatioCard(
                    title: "Push/Pull Ratio",
                    ratio: analytics.muscleGroupBalance.pushPullRatio,
                    ideal: 1.0,
                    description: "Ideal: 1:1"
                )
                
                BalanceRatioCard(
                    title: "Upper/Lower Ratio",
                    ratio: analytics.muscleGroupBalance.upperLowerRatio,
                    ideal: 1.0,
                    description: "Ideal: 1:1"
                )
            }
            
            // Overall balance score
            VStack(spacing: 8) {
                HStack {
                    Text("Balance Score")
                        .font(.subheadline)
                        .fontWeight(.medium)
                    
                    Spacer()
                    
                    Text("\(String(format: "%.0f", analytics.muscleGroupBalance.balanceScore))/100")
                        .font(.headline)
                        .fontWeight(.bold)
                        .foregroundColor(balanceScoreColor(analytics.muscleGroupBalance.balanceScore))
                }
                
                ProgressView(value: analytics.muscleGroupBalance.balanceScore / 100)
                    .progressViewStyle(LinearProgressViewStyle(tint: balanceScoreColor(analytics.muscleGroupBalance.balanceScore)))
            }
            
            // Recommendations
            if !analytics.recommendations.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Recommendations")
                        .font(.subheadline)
                        .fontWeight(.semibold)
                        .foregroundColor(.secondary)
                    
                    ForEach(analytics.recommendations, id: \.self) { recommendation in
                        Text("• \(recommendation)")
                            .font(.caption)
                            .foregroundColor(.primary)
                    }
                }
            }
        }
    }
    
    private func balanceScoreColor(_ score: Double) -> Color {
        if score >= 80 { return .green }
        else if score >= 60 { return .orange }
        else { return .red }
    }
}

struct WeeklyMuscleBar: View {
    let muscle: String
    let value: Double
    let maxValue: Double
    let format: String
    let color: Color
    
    private var fillRatio: Double {
        maxValue > 0 ? value / maxValue : 0
    }
    
    var body: some View {
        HStack {
            Text(muscle.capitalized)
                .font(.caption)
                .fontWeight(.medium)
                .frame(width: 80, alignment: .leading)
            
            ZStack(alignment: .leading) {
                Rectangle()
                    .fill(Color(.systemGray5))
                    .frame(height: 16)
                    .cornerRadius(3)
                
                Rectangle()
                    .fill(color.opacity(0.8))
                    .frame(width: max(2, fillRatio * 180), height: 16)
                    .cornerRadius(3)
                    .animation(.easeInOut(duration: 0.3), value: fillRatio)
            }
            .frame(width: 180)
            
            Spacer()
            
            Text(format)
                .font(.caption)
                .fontWeight(.medium)
                .frame(width: 60, alignment: .trailing)
        }
    }
}

struct BalanceRatioCard: View {
    let title: String
    let ratio: Double
    let ideal: Double
    let description: String
    
    private var ratioStatus: (color: Color, text: String) {
        let diff = abs(ratio - ideal)
        if diff <= 0.2 { return (.green, "Excellent") }
        else if diff <= 0.4 { return (.orange, "Good") }
        else { return (.red, "Needs Work") }
    }
    
    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.caption)
                    .fontWeight(.medium)
                
                Text(description)
                    .font(.caption2)
                    .foregroundColor(.secondary)
            }
            
            Spacer()
            
            VStack(alignment: .trailing, spacing: 2) {
                Text(String(format: "%.1f:1", ratio))
                    .font(.caption)
                    .fontWeight(.bold)
                
                Text(ratioStatus.text)
                    .font(.caption2)
                    .foregroundColor(ratioStatus.color)
            }
        }
        .padding(8)
        .background(Color(.systemGray6))
        .cornerRadius(6)
    }
}

struct WeeklyQuickStats: View {
    let analytics: RoutineAnalytics
    
    var body: some View {
        VStack(spacing: 12) {
            Divider()
            
            HStack {
                Text("Weekly Summary")
                    .font(.subheadline)
                    .fontWeight(.semibold)
                    .foregroundColor(.secondary)
                
                Spacer()
            }
            
            HStack(spacing: 20) {
                QuickStatItem(
                    title: "Total Sets",
                    value: "\(analytics.totalWeeklySets)",
                    color: .blue
                )
                
                QuickStatItem(
                    title: "Total Volume",
                    value: "\(String(format: "%.0f", analytics.totalWeeklyVolume))\(analytics.weightFormat)",
                    color: .green
                )
                
                QuickStatItem(
                    title: "Est. Duration",
                    value: "\(analytics.estimatedWeeklyDuration)min",
                    color: .orange
                )
                
                QuickStatItem(
                    title: "Frequency",
                    value: "\(analytics.frequency)x/week",
                    color: .purple
                )
                
                Spacer()
            }
        }
    }
}

struct QuickStatItem: View {
    let title: String
    let value: String
    let color: Color
    
    var body: some View {
        VStack(spacing: 2) {
            Text(value)
                .font(.subheadline)
                .fontWeight(.bold)
                .foregroundColor(color)
            
            Text(title)
                .font(.caption2)
                .foregroundColor(.secondary)
        }
    }
}

// MARK: - Template Management Section
struct TemplateManagementSection: View {
    @Binding var selectedTemplates: [WorkoutTemplate]
    let onAddTemplate: () -> Void
    let onRemoveTemplate: (WorkoutTemplate) -> Void
    let onReorderTemplates: (IndexSet, Int) -> Void
    
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Workout Templates")
                    .font(.headline)
                
                Spacer()
                
                Button(action: onAddTemplate) {
                    Label("Add Template", systemImage: "plus")
                        .font(.subheadline)
                        .foregroundColor(.white)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 6)
                        .background(WorkoutDesignSystem.primaryBlue)
                        .cornerRadius(6)
                }
            }
            
            if selectedTemplates.isEmpty {
                EmptyTemplatesState(onAddTemplate: onAddTemplate)
            } else {
                Text("\(selectedTemplates.count) template\(selectedTemplates.count == 1 ? "" : "s") selected")
                    .font(.subheadline)
                    .foregroundColor(.secondary)
                
                LazyVStack(spacing: 12) {
                    ForEach(Array(selectedTemplates.enumerated()), id: \.element.id) { index, template in
                        TemplateCard(
                            template: template,
                            dayNumber: index + 1,
                            onRemove: { onRemoveTemplate(template) }
                        )
                    }
                }
            }
        }
        .padding(WorkoutDesignSystem.cardPadding)
        .background(Color(.systemBackground))
        .cornerRadius(WorkoutDesignSystem.cardCornerRadius)
        .shadow(radius: 2)
    }
}

struct EmptyTemplatesState: View {
    let onAddTemplate: () -> Void
    
    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: "calendar.badge.plus")
                .font(.system(size: 40))
                .foregroundColor(.gray)
            
            Text("No templates selected")
                .font(.subheadline)
                .foregroundColor(.secondary)
            
            Text("Add workout templates to create your routine")
                .font(.caption)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
            
            Button(action: onAddTemplate) {
                Label("Add Template", systemImage: "plus")
                    .padding(.horizontal, 16)
                    .padding(.vertical, 8)
                    .background(WorkoutDesignSystem.primaryBlue)
                    .foregroundColor(.white)
                    .cornerRadius(8)
            }
        }
        .padding()
        .frame(maxWidth: .infinity)
        .background(WorkoutDesignSystem.cardBackground)
        .cornerRadius(WorkoutDesignSystem.cardCornerRadius)
    }
}

struct TemplateCard: View {
    let template: WorkoutTemplate
    let dayNumber: Int
    let onRemove: () -> Void
    
    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text("Day \(dayNumber)")
                        .font(.caption)
                        .fontWeight(.medium)
                        .foregroundColor(.secondary)
                    
                    Spacer()
                    
                    Button(action: onRemove) {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundColor(.red)
                    }
                }
                
                Text(template.name)
                    .font(.subheadline)
                    .fontWeight(.semibold)
                
                if let description = template.description {
                    Text(description)
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .lineLimit(2)
                }
                
                HStack {
                    Text("\(template.exercises.count) exercises")
                        .font(.caption)
                        .foregroundColor(.secondary)
                    
                    // Duration will be calculated by analytics
                    
                    Spacer()
                }
            }
            
            Spacer()
        }
        .padding(12)
        .background(WorkoutDesignSystem.cardBackground)
        .cornerRadius(8)
    }
}

// MARK: - Template Selection Sheet
struct TemplateSelectionSheet: View {
    let availableTemplates: [WorkoutTemplate]
    let selectedTemplateIds: Set<String>
    let onTemplateSelected: (WorkoutTemplate) -> Void
    @Environment(\.presentationMode) var presentationMode
    
    var body: some View {
        NavigationView {
            List {
                ForEach(availableTemplates) { template in
                    TemplateSelectionRow(
                        template: template,
                        isSelected: selectedTemplateIds.contains(template.id),
                        onSelect: {
                            onTemplateSelected(template)
                            presentationMode.wrappedValue.dismiss()
                        }
                    )
                }
            }
            .navigationTitle("Select Template")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Done") {
                        presentationMode.wrappedValue.dismiss()
                    }
                }
            }
        }
    }
}

struct TemplateSelectionRow: View {
    let template: WorkoutTemplate
    let isSelected: Bool
    let onSelect: () -> Void
    
    var body: some View {
        Button(action: onSelect) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text(template.name)
                        .font(.headline)
                        .foregroundColor(.primary)
                    
                    if let description = template.description {
                        Text(description)
                            .font(.subheadline)
                            .foregroundColor(.secondary)
                            .lineLimit(2)
                    }
                    
                    Text("\(template.exercises.count) exercises")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                
                Spacer()
                
                if isSelected {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundColor(.green)
                } else {
                    Image(systemName: "plus.circle")
                        .foregroundColor(.blue)
                }
            }
        }
        .buttonStyle(PlainButtonStyle())
    }
}

// MARK: - Routine Action Buttons
struct RoutineActionButtons: View {
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
                        Text("Save Routine")
                    }
                }
            }
            .buttonStyle(TemplatePrimaryButtonStyle())
            .disabled(isSaving || !canSave)
        }
    }
}

#Preview {
    RoutineEditorView { routine in
        print("Routine saved: \(routine.name)")
    }
} 