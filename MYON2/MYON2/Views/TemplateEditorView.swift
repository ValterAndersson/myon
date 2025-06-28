import SwiftUI

struct TemplateEditorView: View {
    @StateObject private var templateManager = TemplateManager.shared
    @StateObject private var exercisesViewModel = ExercisesViewModel()
    @Environment(\.dismiss) private var dismiss
    
    let existingTemplate: WorkoutTemplate?
    
    @State private var showingExerciseSelector = false
    @State private var showingSaveAlert = false
    @State private var saveError: String?
    
    init(template: WorkoutTemplate? = nil) {
        self.existingTemplate = template
    }
    
    var body: some View {
        NavigationView {
            ScrollView {
                VStack(spacing: 20) {
                    // Template Metadata
                    TemplateMetadataSection()
                    
                    // Exercise Configuration
                    ExerciseConfigurationSection()
                    
                    // Muscle Stimulus Projection (Real-time feedback)
                    if templateManager.currentTemplate?.exercises.isEmpty == false {
                        MuscleStimulusSection()
                    }
                    
                    // Action Buttons
                    ActionButtonsSection()
                }
                .padding()
            }
            .navigationTitle(existingTemplate == nil ? "New Template" : "Edit Template")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Cancel") {
                        templateManager.stopEditing()
                        dismiss()
                    }
                }
                
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Save") {
                        saveTemplate()
                    }
                    .disabled(templateManager.currentTemplate?.name.isEmpty != false)
                }
            }
            .sheet(isPresented: $showingExerciseSelector) {
                ExerciseSelectionView { exercise in
                    templateManager.addExercise(exercise)
                    showingExerciseSelector = false
                }
            }
            .alert("Save Error", isPresented: .constant(saveError != nil)) {
                Button("OK") {
                    saveError = nil
                }
            } message: {
                Text(saveError ?? "")
            }
        }
        .onAppear {
            templateManager.startEditing(template: existingTemplate)
        }
        .onDisappear {
            templateManager.stopEditing()
        }
    }
    
    // MARK: - Template Metadata Section
    @ViewBuilder
    private func TemplateMetadataSection() -> some View {
        VStack(spacing: 16) {
            TemplateMetadataForm(
                name: Binding(
                    get: { templateManager.currentTemplate?.name ?? "" },
                    set: { templateManager.updateName($0) }
                ),
                description: Binding(
                    get: { templateManager.currentTemplate?.description ?? "" },
                    set: { templateManager.updateDescription($0.isEmpty ? nil : $0) }
                )
            )
        }
        .padding(.horizontal)
    }
    
    // MARK: - Exercise Configuration Section
    @ViewBuilder
    private func ExerciseConfigurationSection() -> some View {
        VStack(spacing: 16) {
            HStack {
                Text("Exercise Configuration")
                    .font(.headline)
                    .fontWeight(.semibold)
                
                Spacer()
                
                Button(action: {
                    showingExerciseSelector = true
                }) {
                    HStack(spacing: 4) {
                        Image(systemName: "plus")
                        Text("Add Exercise")
                    }
                    .font(.subheadline)
                    .foregroundColor(.white)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 8)
                    .background(Color.blue)
                    .cornerRadius(8)
                }
            }
            
            if let exercises = templateManager.currentTemplate?.exercises, !exercises.isEmpty {
                ForEach(exercises.indices, id: \.self) { index in
                    TemplateExerciseCard(
                        exercise: exercises[index],
                        onRemove: {
                            templateManager.removeExercise(id: exercises[index].id)
                        },
                        onAddSet: {
                            templateManager.addSet(toExerciseId: exercises[index].id)
                        },
                        onRemoveSet: { setId in
                            templateManager.removeSet(exerciseId: exercises[index].id, setId: setId)
                        }
                    )
                }
            } else {
                Text("No exercises added yet")
                    .foregroundColor(.secondary)
                    .padding(.vertical, 40)
            }
        }
        .padding(.horizontal)
    }
    
    // MARK: - Muscle Stimulus Section
    @ViewBuilder
    private func MuscleStimulusSection() -> some View {
        VStack(spacing: 16) {
            if let analytics = templateManager.currentAnalytics {
                MuscleStimulusProjection(analytics: analytics)
                TemplateBalanceGuidance(analytics: analytics)
            } else {
                MuscleStimulusProjectionSkeleton()
            }
        }
        .padding(.horizontal)
    }
    
    // MARK: - Action Buttons Section
    @ViewBuilder
    private func ActionButtonsSection() -> some View {
        VStack(spacing: 12) {
            Button(action: {
                saveTemplate()
            }) {
                Text("Save Template")
                    .font(.subheadline)
                    .fontWeight(.semibold)
                    .foregroundColor(.white)
                    .frame(maxWidth: .infinity)
                    .padding()
                    .background(Color.blue)
                    .cornerRadius(12)
            }
            .disabled(templateManager.currentTemplate?.name.isEmpty != false)
            
            Button(action: {
                templateManager.stopEditing()
                dismiss()
            }) {
                Text("Cancel")
                    .font(.subheadline)
                    .foregroundColor(.red)
                    .frame(maxWidth: .infinity)
                    .padding()
                    .background(Color.clear)
                    .overlay(
                        RoundedRectangle(cornerRadius: 12)
                            .stroke(Color.red, lineWidth: 1)
                    )
            }
        }
        .padding(.horizontal)
        .padding(.bottom, 20)
    }
    
    // MARK: - Actions
    private func saveTemplate() {
        guard let template = templateManager.currentTemplate, !template.name.isEmpty else {
            saveError = "Template name is required"
            return
        }
        
        Task {
            do {
                let templateId = try await templateManager.saveTemplate()
                await MainActor.run {
                    templateManager.stopEditing()
                    dismiss()
                }
            } catch {
                await MainActor.run {
                    saveError = "Failed to save template: \(error.localizedDescription)"
                }
            }
        }
    }
}

// MARK: - Empty Template Exercise State
struct EmptyTemplateExerciseState: View {
    let onAddExercise: () -> Void
    
    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: "dumbbell")
                .font(.system(size: 40))
                .foregroundColor(.gray)
            
            Text("No exercises added")
                .font(.subheadline)
                .foregroundColor(.secondary)
            
            Text("Add exercises to create your template")
                .font(.caption)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
            
            Button(action: onAddExercise) {
                Label("Add Exercise", systemImage: "plus")
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

// MARK: - Template from Active Workout
struct SaveTemplateFromWorkoutView: View {
    let activeWorkout: ActiveWorkout
    let onSave: (WorkoutTemplate) -> Void
    @Environment(\.presentationMode) var presentationMode
    @StateObject private var templateRepository = TemplateRepository()
    
    @State private var templateName: String = ""
    @State private var templateDescription: String = ""
    @State private var isSaving = false
    
    var body: some View {
        NavigationView {
            ScrollView {
                VStack(spacing: 20) {
                    // Header
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Save as Template")
                            .font(.title2)
                            .fontWeight(.semibold)
                        
                        Text("Create a template from your current workout")
                            .font(.subheadline)
                            .foregroundColor(.secondary)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal)
                    
                    // Template form (Simplified)
                    TemplateMetadataForm(
                        name: $templateName,
                        description: $templateDescription
                    )
                    .padding(.horizontal)
                    
                    // Preview exercises
                    VStack(alignment: .leading, spacing: 12) {
                        Text("Exercises to Include")
                            .font(.headline)
                            .padding(.horizontal)
                        
                        LazyVStack(spacing: 12) {
                            ForEach(activeWorkout.exercises) { exercise in
                                TemplatePreviewCard(exercise: exercise)
                            }
                        }
                        .padding(.horizontal)
                    }
                    
                    // Save button
                    TemplateActionButtons(
                        onSave: saveTemplateFromWorkout,
                        onCancel: { presentationMode.wrappedValue.dismiss() },
                        isSaving: isSaving,
                        canSave: !templateName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                    )
                    .padding(.horizontal)
                    .padding(.bottom, 40)
                }
            }
            .navigationTitle("Save Template")
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
        .onAppear {
            // AI will calculate duration based on exercises
        }
    }
    
    private func saveTemplateFromWorkout() {
        isSaving = true
        
        // Convert ActiveWorkout to WorkoutTemplate
        let templateExercises = activeWorkout.exercises.map { activeExercise in
            WorkoutTemplateExercise(
                id: UUID().uuidString,
                exerciseId: activeExercise.exerciseId,
                position: activeExercise.position,
                sets: activeExercise.sets.map { activeSet in
                    WorkoutTemplateSet(
                        id: UUID().uuidString,
                        reps: activeSet.reps,
                        rir: activeSet.rir,
                        type: activeSet.type,
                        weight: activeSet.weight,
                        duration: nil
                    )
                },
                restBetweenSets: nil
            )
        }
        
        let template = WorkoutTemplate(
            id: UUID().uuidString,
            userId: activeWorkout.userId,
            name: templateName,
            description: templateDescription.isEmpty ? nil : templateDescription,
            exercises: templateExercises,
            createdAt: Date(),
            updatedAt: Date()
        )
        
        // Use repository for saving (will leverage cloud functions for AI analysis)
        Task {
            do {
                let _ = try await templateRepository.createTemplate(template)
                
                await MainActor.run {
                    onSave(template)
                    isSaving = false
                    presentationMode.wrappedValue.dismiss()
                }
            } catch {
                await MainActor.run {
                    print("Error saving template from workout: \(error)")
                    isSaving = false
                }
            }
        }
    }
}

// MARK: - Template Preview Card
struct TemplatePreviewCard: View {
    let exercise: ActiveExercise
    
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(exercise.name.capitalized)
                .font(.headline)
            
            if !exercise.sets.isEmpty {
                Text("\(exercise.sets.count) sets configured")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .background(WorkoutDesignSystem.cardBackground)
        .cornerRadius(8)
    }
}

// MARK: - Muscle Stimulus Projection Skeleton
struct MuscleStimulusProjectionSkeleton: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Muscle Stimulus Projection")
                .font(.headline)
                .fontWeight(.semibold)
            
            VStack(spacing: 12) {
                ForEach(0..<5, id: \.self) { _ in
                    HStack {
                        Text("Muscle Group")
                            .font(.subheadline)
                            .fontWeight(.medium)
                            .frame(width: 80, alignment: .leading)
                            .foregroundColor(.secondary)
                        
                        Rectangle()
                            .fill(Color(.systemGray5))
                            .frame(height: 20)
                            .cornerRadius(4)
                        
                        Text("0kg")
                            .font(.subheadline)
                            .fontWeight(.semibold)
                            .foregroundColor(.secondary)
                            .frame(width: 60)
                    }
                }
            }
            
            Text("Add exercises with sets to see muscle stimulus projection")
                .font(.caption)
                .foregroundColor(.secondary)
                .frame(maxWidth: .infinity, alignment: .center)
                .padding(.top, 8)
        }
        .padding(WorkoutDesignSystem.cardPadding)
        .background(Color(.systemBackground))
        .cornerRadius(WorkoutDesignSystem.cardCornerRadius)
        .shadow(radius: 2)
    }
}

#Preview {
    TemplateEditorView()
} 