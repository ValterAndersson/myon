/**
 * FocusModeWorkoutScreen.swift
 * 
 * Full-screen workout execution view.
 * 
 * Design principles (per PRD):
 * - Spreadsheet-first: exercises as sections, sets as rows, max space utilization
 * - All sets expanded by default (no collapsed state)
 * - Fast editing: tap cell → inline dock with stepper controls
 * - Non-intrusive AI: optional copilot actions, never blocking
 */

import SwiftUI

struct FocusModeWorkoutScreen: View {
    @StateObject private var service = FocusModeWorkoutService.shared
    @Environment(\.dismiss) private var dismiss
    
    // Workout source (template, routine, or empty)
    let sourceTemplateId: String?
    let sourceRoutineId: String?
    let workoutName: String?
    
    // Local UI state
    @State private var selectedCell: FocusModeGridCell?
    @State private var showingExerciseSearch = false
    @State private var showingCancelConfirmation = false
    @State private var showingCompleteConfirmation = false
    
    init(
        templateId: String? = nil,
        routineId: String? = nil,
        name: String? = nil
    ) {
        self.sourceTemplateId = templateId
        self.sourceRoutineId = routineId
        self.workoutName = name
    }
    
    var body: some View {
        NavigationStack {
            ZStack {
                ColorsToken.Background.primary.ignoresSafeArea()
                
                if service.isLoading {
                    loadingView
                } else if let workout = service.workout {
                    workoutContent(workout)
                } else {
                    emptyStartView
                }
            }
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button {
                        if service.workout != nil {
                            showingCancelConfirmation = true
                        } else {
                            dismiss()
                        }
                    } label: {
                        Image(systemName: "xmark")
                            .font(.system(size: 16, weight: .medium))
                            .foregroundColor(ColorsToken.Text.primary)
                    }
                }
                
                ToolbarItem(placement: .principal) {
                    workoutTimer
                }
                
                ToolbarItem(placement: .navigationBarTrailing) {
                    if service.workout != nil {
                        Button("Finish") {
                            showingCompleteConfirmation = true
                        }
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundColor(ColorsToken.Brand.primary)
                    }
                }
            }
        }
        .interactiveDismissDisabled(service.workout != nil)
        .confirmationDialog("Cancel Workout?", isPresented: $showingCancelConfirmation) {
            Button("Discard Workout", role: .destructive) {
                dismiss()
            }
            Button("Keep Logging", role: .cancel) { }
        } message: {
            Text("Your progress will not be saved.")
        }
        .confirmationDialog("Finish Workout?", isPresented: $showingCompleteConfirmation) {
            Button("Complete Workout") {
                Task {
                    // TODO: Complete workout and show summary
                    dismiss()
                }
            }
            Button("Keep Logging", role: .cancel) { }
        }
        .sheet(isPresented: $showingExerciseSearch) {
            FocusModeExerciseSearch { exercise in
                addExercise(exercise)
            }
        }
        .task {
            await startWorkoutIfNeeded()
        }
    }
    
    // MARK: - Workout Content
    
    @ViewBuilder
    private func workoutContent(_ workout: FocusModeWorkout) -> some View {
        ScrollView {
            LazyVStack(spacing: 0, pinnedViews: []) {
                // Exercises - each as a section with full set grid
                ForEach(workout.exercises) { exercise in
                    FocusModeExerciseSection(
                        exercise: exercise,
                        selectedCell: $selectedCell,
                        onLogSet: logSet,
                        onPatchField: patchField,
                        onAddSet: { addSet(to: exercise.instanceId) },
                        onRemoveSet: { setId in removeSet(exerciseId: exercise.instanceId, setId: setId) },
                        onAutofill: { autofillExercise(exercise.instanceId) }
                    )
                }
                
                // Add Exercise Button
                addExerciseButton
                    .padding(.top, Space.lg)
                    .padding(.bottom, 100) // Extra padding for keyboard/editing dock
            }
            .padding(.horizontal, Space.md)
        }
        .scrollDismissesKeyboard(.interactively)
        
        // Floating totals bar at bottom
        if !workout.exercises.isEmpty {
            VStack {
                Spacer()
                workoutTotalsBar(workout.totals)
            }
        }
    }
    
    // MARK: - Loading View
    
    private var loadingView: some View {
        VStack(spacing: Space.lg) {
            ProgressView()
                .scaleEffect(1.2)
            Text("Starting workout...")
                .font(.system(size: 15))
                .foregroundColor(ColorsToken.Text.secondary)
        }
    }
    
    // MARK: - Empty Start View
    
    private var emptyStartView: some View {
        VStack(spacing: Space.xl) {
            Image(systemName: "figure.strengthtraining.traditional")
                .font(.system(size: 48))
                .foregroundColor(ColorsToken.Brand.primary)
            
            Text("Ready to Lift")
                .font(.system(size: 22, weight: .semibold))
                .foregroundColor(ColorsToken.Text.primary)
            
            Text("Start an empty workout and add exercises as you go")
                .font(.system(size: 15))
                .foregroundColor(ColorsToken.Text.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, Space.xl)
            
            Button {
                Task {
                    await startEmptyWorkout()
                }
            } label: {
                Text("Start Empty Workout")
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(.white)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 14)
                    .background(ColorsToken.Brand.primary)
                    .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.medium))
            }
            .padding(.horizontal, Space.xl)
        }
    }
    
    // MARK: - Workout Timer
    
    private var workoutTimer: some View {
        Group {
            if let workout = service.workout {
                let duration = Date().timeIntervalSince(workout.startTime)
                Text(formatDuration(duration))
                    .font(.system(size: 17, weight: .semibold).monospacedDigit())
                    .foregroundColor(ColorsToken.Text.primary)
            } else {
                Text("Focus Mode")
                    .font(.system(size: 17, weight: .semibold))
                    .foregroundColor(ColorsToken.Text.primary)
            }
        }
    }
    
    // MARK: - Add Exercise Button
    
    private var addExerciseButton: some View {
        Button { showingExerciseSearch = true } label: {
            HStack(spacing: Space.sm) {
                Image(systemName: "plus.circle.fill")
                    .font(.system(size: 20))
                Text("Add Exercise")
                    .font(.system(size: 15, weight: .medium))
            }
            .foregroundColor(ColorsToken.Brand.primary)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 16)
            .background(ColorsToken.Brand.primary.opacity(0.08))
            .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.medium))
        }
        .buttonStyle(PlainButtonStyle())
    }
    
    // MARK: - Workout Totals Bar
    
    private func workoutTotalsBar(_ totals: WorkoutTotals) -> some View {
        HStack(spacing: Space.lg) {
            totalsStat(value: "\(totals.sets)", label: "Sets")
            totalsStat(value: "\(totals.reps)", label: "Reps")
            totalsStat(value: formatVolume(totals.volume), label: "Volume")
            
            Spacer()
            
            if service.isSyncing {
                ProgressView()
                    .scaleEffect(0.8)
            }
        }
        .padding(.horizontal, Space.lg)
        .padding(.vertical, Space.md)
        .background(
            ColorsToken.Surface.elevated
                .shadow(color: .black.opacity(0.1), radius: 8, y: -2)
        )
    }
    
    private func totalsStat(value: String, label: String) -> some View {
        VStack(spacing: 2) {
            Text(value)
                .font(.system(size: 18, weight: .bold).monospacedDigit())
                .foregroundColor(ColorsToken.Text.primary)
            Text(label)
                .font(.system(size: 11))
                .foregroundColor(ColorsToken.Text.secondary)
        }
    }
    
    // MARK: - Actions
    
    private func startWorkoutIfNeeded() async {
        guard service.workout == nil else { return }
        
        if sourceTemplateId != nil || sourceRoutineId != nil {
            do {
                _ = try await service.startWorkout(
                    name: workoutName,
                    sourceTemplateId: sourceTemplateId,
                    sourceRoutineId: sourceRoutineId
                )
            } catch {
                print("Failed to start workout: \(error)")
            }
        }
    }
    
    private func startEmptyWorkout() async {
        do {
            _ = try await service.startWorkout(name: "Quick Workout")
        } catch {
            print("Failed to start workout: \(error)")
        }
    }
    
    private func addExercise(_ exercise: Exercise) {
        Task {
            do {
                try await service.addExercise(exercise: exercise)
            } catch {
                print("Add exercise failed: \(error)")
            }
        }
    }
    
    private func logSet(exerciseId: String, setId: String, weight: Double?, reps: Int, rir: Int?) {
        Task {
            do {
                _ = try await service.logSet(
                    exerciseInstanceId: exerciseId,
                    setId: setId,
                    weight: weight,
                    reps: reps,
                    rir: rir
                )
                UIImpactFeedbackGenerator(style: .medium).impactOccurred()
            } catch {
                print("Log set failed: \(error)")
            }
        }
    }
    
    private func patchField(exerciseId: String, setId: String, field: String, value: Any) {
        Task {
            do {
                _ = try await service.patchField(
                    exerciseInstanceId: exerciseId,
                    setId: setId,
                    field: field,
                    value: value
                )
            } catch {
                print("Patch failed: \(error)")
            }
        }
    }
    
    private func addSet(to exerciseId: String) {
        Task {
            do {
                _ = try await service.addSet(exerciseInstanceId: exerciseId)
                UIImpactFeedbackGenerator(style: .light).impactOccurred()
            } catch {
                print("Add set failed: \(error)")
            }
        }
    }
    
    private func removeSet(exerciseId: String, setId: String) {
        Task {
            do {
                _ = try await service.removeSet(exerciseInstanceId: exerciseId, setId: setId)
            } catch {
                print("Remove set failed: \(error)")
            }
        }
    }
    
    private func autofillExercise(_ exerciseId: String) {
        // TODO: Get AI prescription and call autofillExercise
        UIImpactFeedbackGenerator(style: .medium).impactOccurred()
    }
    
    // MARK: - Helpers
    
    private func formatDuration(_ interval: TimeInterval) -> String {
        let hours = Int(interval) / 3600
        let minutes = (Int(interval) % 3600) / 60
        let seconds = Int(interval) % 60
        
        if hours > 0 {
            return String(format: "%d:%02d:%02d", hours, minutes, seconds)
        }
        return String(format: "%02d:%02d", minutes, seconds)
    }
    
    private func formatVolume(_ volume: Double) -> String {
        if volume >= 1000 {
            return String(format: "%.1fk", volume / 1000)
        }
        return "\(Int(volume))"
    }
}

// MARK: - Exercise Section

struct FocusModeExerciseSection: View {
    let exercise: FocusModeExercise
    @Binding var selectedCell: FocusModeGridCell?
    
    let onLogSet: (String, String, Double?, Int, Int?) -> Void
    let onPatchField: (String, String, String, Any) -> Void
    let onAddSet: () -> Void
    let onRemoveSet: (String) -> Void
    let onAutofill: () -> Void
    
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Exercise Header
            exerciseHeader
            
            // AI Actions Row (non-intrusive)
            aiActionsRow
            
            // Set Grid - EXPANDED by default, using full width
            FocusModeSetGrid(
                exercise: exercise,
                selectedCell: $selectedCell,
                onLogSet: onLogSet,
                onPatchField: onPatchField,
                onAddSet: onAddSet,
                onRemoveSet: onRemoveSet
            )
        }
        .background(ColorsToken.Surface.card)
        .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.medium))
        .padding(.top, Space.md)
    }
    
    private var exerciseHeader: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(exercise.name)
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(ColorsToken.Text.primary)
                
                Text("\(exercise.completedSetsCount)/\(exercise.totalWorkingSetsCount) sets")
                    .font(.system(size: 13))
                    .foregroundColor(ColorsToken.Text.secondary)
            }
            
            Spacer()
            
            // Progress indicator
            if exercise.isComplete {
                Image(systemName: "checkmark.circle.fill")
                    .foregroundColor(ColorsToken.State.success)
                    .font(.system(size: 20))
            }
            
            // More menu
            Menu {
                Button { onAutofill() } label: {
                    Label("Auto-fill Sets", systemImage: "sparkles")
                }
                Button(role: .destructive) {
                    // TODO: Remove exercise
                } label: {
                    Label("Remove Exercise", systemImage: "trash")
                }
            } label: {
                Image(systemName: "ellipsis")
                    .font(.system(size: 16))
                    .foregroundColor(ColorsToken.Text.secondary)
                    .frame(width: 32, height: 32)
            }
        }
        .padding(.horizontal, Space.md)
        .padding(.vertical, Space.sm)
    }
    
    private var aiActionsRow: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: Space.sm) {
                aiActionButton(icon: "sparkles", label: "Auto-fill") {
                    onAutofill()
                }
                aiActionButton(icon: "arrow.up", label: "+2.5kg") {
                    // Suggest weight increase
                }
                aiActionButton(icon: "clock.arrow.circlepath", label: "Last Time") {
                    // Use last performance
                }
            }
            .padding(.horizontal, Space.md)
            .padding(.bottom, Space.sm)
        }
    }
    
    private func aiActionButton(icon: String, label: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 4) {
                Image(systemName: icon)
                    .font(.system(size: 11, weight: .medium))
                Text(label)
                    .font(.system(size: 12, weight: .medium))
            }
            .foregroundColor(ColorsToken.Brand.primary)
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(ColorsToken.Brand.primary.opacity(0.08))
            .clipShape(Capsule())
        }
        .buttonStyle(PlainButtonStyle())
    }
}

// MARK: - Grid Cell Selection

enum FocusModeGridCell: Equatable, Hashable {
    case weight(exerciseId: String, setId: String)
    case reps(exerciseId: String, setId: String)
    case rir(exerciseId: String, setId: String)
    case done(exerciseId: String, setId: String)
    
    var exerciseId: String {
        switch self {
        case .weight(let id, _), .reps(let id, _), .rir(let id, _), .done(let id, _):
            return id
        }
    }
    
    var setId: String {
        switch self {
        case .weight(_, let id), .reps(_, let id), .rir(_, let id), .done(_, let id):
            return id
        }
    }
}

// MARK: - Exercise Search Sheet (Placeholder)

private struct ExerciseSearchSheet: View {
    let onSelect: (Exercise) -> Void
    @Environment(\.dismiss) private var dismiss
    
    var body: some View {
        NavigationStack {
            Text("Exercise Search")
                .navigationTitle("Add Exercise")
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .navigationBarLeading) {
                        Button("Cancel") { dismiss() }
                    }
                }
        }
    }
}

// MARK: - Preview

#Preview {
    FocusModeWorkoutScreen()
}
