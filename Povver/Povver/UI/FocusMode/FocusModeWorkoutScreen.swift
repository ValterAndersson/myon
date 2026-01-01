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
    @State private var showingSettings = false
    @State private var showingAIPanel = false
    @State private var showingNameEditor = false
    @State private var showingStartTimeEditor = false
    @State private var elapsedTime: TimeInterval = 0
    @State private var timer: Timer?
    @State private var isEditingOrder = false
    @State private var editingName: String = ""
    
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
        VStack(spacing: 0) {
            // Custom header bar (always visible)
            customHeaderBar
            
            // Main content
            ZStack {
                ColorsToken.Background.primary.ignoresSafeArea()
                
                if service.isLoading {
                    loadingView
                } else if let workout = service.workout {
                    workoutContent(workout)
                } else {
                    workoutStartView
                }
            }
        }
        .background(ColorsToken.Background.primary)
        .navigationBarHidden(true)  // Hide system nav bar, use custom
        .interactiveDismissDisabled(service.workout != nil)
        .confirmationDialog("Workout Options", isPresented: $showingSettings) {
            Button("Discard Workout", role: .destructive) {
                stopTimer()
                Task {
                    // TODO: Cancel workout via service
                }
                dismiss()
            }
            Button("Keep Logging", role: .cancel) { }
        } message: {
            Text("Your progress will not be saved if you discard.")
        }
        .confirmationDialog("Finish Workout?", isPresented: $showingCompleteConfirmation) {
            Button("Complete Workout") {
                stopTimer()
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
        .sheet(isPresented: $showingAIPanel) {
            aiPanelPlaceholder
        }
        .task {
            await startWorkoutIfNeeded()
        }
    }
    
    // MARK: - Workout Start View
    
    private var workoutStartView: some View {
        ScrollView {
            VStack(spacing: Space.xl) {
                Spacer(minLength: 40)
                
                // Icon
                Image(systemName: "figure.strengthtraining.traditional")
                    .font(.system(size: 48))
                    .foregroundColor(ColorsToken.Brand.primary)
                
                Text("Start a Workout")
                    .font(.system(size: 24, weight: .bold))
                    .foregroundColor(ColorsToken.Text.primary)
                
                // Start Options
                VStack(spacing: Space.md) {
                    // Empty Workout
                    startOptionButton(
                        icon: "plus.circle.fill",
                        title: "Start Empty Workout",
                        subtitle: "Add exercises as you go",
                        isPrimary: true
                    ) {
                        Task { await startEmptyWorkout() }
                    }
                    
                    // Next Scheduled (placeholder - would need routine cursor)
                    startOptionButton(
                        icon: "calendar",
                        title: "Next Scheduled",
                        subtitle: "No routine set up",
                        isDisabled: true
                    ) {
                        // TODO: Start from routine cursor
                    }
                    
                    // From Template
                    startOptionButton(
                        icon: "doc.on.doc",
                        title: "From Template",
                        subtitle: "Choose from saved templates",
                        isDisabled: false
                    ) {
                        // TODO: Show template picker
                    }
                }
                .padding(.horizontal, Space.lg)
                
                Spacer()
            }
            .padding(.top, Space.xl)
        }
    }
    
    private func startOptionButton(
        icon: String,
        title: String,
        subtitle: String,
        isPrimary: Bool = false,
        isDisabled: Bool = false,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            HStack(spacing: Space.md) {
                Image(systemName: icon)
                    .font(.system(size: 20))
                    .foregroundColor(isDisabled ? ColorsToken.Text.muted : (isPrimary ? .white : ColorsToken.Brand.primary))
                    .frame(width: 32)
                
                VStack(alignment: .leading, spacing: 2) {
                    Text(title)
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundColor(isDisabled ? ColorsToken.Text.muted : (isPrimary ? .white : ColorsToken.Text.primary))
                    
                    Text(subtitle)
                        .font(.system(size: 13))
                        .foregroundColor(isDisabled ? ColorsToken.Text.muted : (isPrimary ? .white.opacity(0.8) : ColorsToken.Text.secondary))
                }
                
                Spacer()
                
                Image(systemName: "chevron.right")
                    .font(.system(size: 14, weight: .medium))
                    .foregroundColor(isDisabled ? ColorsToken.Text.muted : (isPrimary ? .white.opacity(0.8) : ColorsToken.Text.secondary))
            }
            .padding(.horizontal, Space.lg)
            .padding(.vertical, 16)
            .background(isPrimary ? ColorsToken.Brand.primary : ColorsToken.Surface.card)
            .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.medium))
        }
        .buttonStyle(PlainButtonStyle())
        .disabled(isDisabled)
        .opacity(isDisabled ? 0.6 : 1)
    }
    
    // MARK: - Workout Content
    
    @ViewBuilder
    private func workoutContent(_ workout: FocusModeWorkout) -> some View {
        if isEditingOrder {
            // Edit mode: simplified list with drag handles
            VStack(spacing: 0) {
                // Header
                HStack {
                    Text("Drag to reorder exercises")
                        .font(.system(size: 13))
                        .foregroundColor(ColorsToken.Text.secondary)
                    Spacer()
                }
                .padding(.horizontal, Space.lg)
                .padding(.vertical, Space.sm)
                .background(ColorsToken.Background.secondary.opacity(0.5))
                
                List {
                    ForEach(workout.exercises) { exercise in
                        exerciseReorderRow(exercise)
                            .listRowBackground(ColorsToken.Surface.card)
                            .listRowInsets(EdgeInsets(top: 8, leading: 16, bottom: 8, trailing: 16))
                    }
                    .onMove { from, to in
                        reorderExercises(from: from, to: to)
                    }
                }
                .listStyle(.plain)
                .environment(\.editMode, .constant(.active))
            }
        } else {
            // Normal mode: full exercise sections
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
                        .padding(.bottom, 40)
                }
                .padding(.horizontal, Space.md)
            }
            .scrollDismissesKeyboard(.interactively)
        }
    }
    
    // MARK: - Exercise Reorder Row
    
    private func exerciseReorderRow(_ exercise: FocusModeExercise) -> some View {
        HStack(spacing: Space.md) {
            VStack(alignment: .leading, spacing: 2) {
                Text(exercise.name)
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundColor(ColorsToken.Text.primary)
                
                Text("\(exercise.completedSetsCount)/\(exercise.totalWorkingSetsCount) sets")
                    .font(.system(size: 13))
                    .foregroundColor(ColorsToken.Text.secondary)
            }
            
            Spacer()
            
            if exercise.isComplete {
                Image(systemName: "checkmark.circle.fill")
                    .foregroundColor(ColorsToken.State.success)
                    .font(.system(size: 18))
            }
        }
        .padding(.vertical, 4)
    }
    
    // MARK: - Reorder Exercises
    
    private func reorderExercises(from source: IndexSet, to destination: Int) {
        // TODO: Call service to reorder exercises
        // For now this just triggers UI feedback
        UIImpactFeedbackGenerator(style: .medium).impactOccurred()
        
        // The actual reorder would need to:
        // 1. Update positions in Firestore
        // 2. Refresh the workout from service
        print("Reorder from \(source) to \(destination)")
    }
    
    // MARK: - Custom Header Bar
    
    private var customHeaderBar: some View {
        VStack(spacing: 0) {
            HStack(alignment: .center, spacing: Space.sm) {
                // Left side: Name + Start time (stacked)
                if let workout = service.workout {
                    VStack(alignment: .leading, spacing: 2) {
                        // Tappable workout name
                        Button {
                            editingName = workout.name ?? "Workout"
                            showingNameEditor = true
                        } label: {
                            HStack(spacing: 4) {
                                Text(workout.name ?? "Workout")
                                    .font(.system(size: 16, weight: .semibold))
                                    .foregroundColor(ColorsToken.Text.primary)
                                    .lineLimit(1)
                                
                                Image(systemName: "chevron.down")
                                    .font(.system(size: 10, weight: .medium))
                                    .foregroundColor(ColorsToken.Text.secondary)
                            }
                        }
                        .buttonStyle(PlainButtonStyle())
                        
                        // Start time (tappable)
                        Button {
                            showingStartTimeEditor = true
                        } label: {
                            HStack(spacing: 4) {
                                Image(systemName: "calendar")
                                    .font(.system(size: 11))
                                Text(formatStartTime(workout.startTime))
                                    .font(.system(size: 12))
                            }
                            .foregroundColor(ColorsToken.Text.secondary)
                        }
                        .buttonStyle(PlainButtonStyle())
                    }
                    
                    Spacer()
                    
                    // Timer (centered-ish)
                    Text(formatDuration(elapsedTime))
                        .font(.system(size: 14, weight: .medium).monospacedDigit())
                        .foregroundColor(ColorsToken.Text.secondary)
                        .padding(.horizontal, Space.sm)
                    
                    // Right side: Actions
                    HStack(spacing: Space.sm) {
                        // Settings/More button
                        Menu {
                            Button {
                                editingName = workout.name ?? "Workout"
                                showingNameEditor = true
                            } label: {
                                Label("Edit Name", systemImage: "pencil")
                            }
                            
                            Button {
                                showingStartTimeEditor = true
                            } label: {
                                Label("Edit Start Time", systemImage: "calendar")
                            }
                            
                            Divider()
                            
                            Button(role: .destructive) {
                                showingCancelConfirmation = true
                            } label: {
                                Label("Discard Workout", systemImage: "trash")
                            }
                        } label: {
                            Image(systemName: "ellipsis.circle")
                                .font(.system(size: 20))
                                .foregroundColor(ColorsToken.Text.secondary)
                        }
                        
                        // AI button
                        Button {
                            showingAIPanel = true
                        } label: {
                            Image(systemName: "sparkles")
                                .font(.system(size: 18))
                                .foregroundColor(ColorsToken.Brand.primary)
                        }
                        
                        // Finish button (prominent)
                        Button {
                            showingCompleteConfirmation = true
                        } label: {
                            Text("Finish")
                                .font(.system(size: 14, weight: .semibold))
                                .foregroundColor(.white)
                                .padding(.horizontal, 12)
                                .padding(.vertical, 6)
                                .background(ColorsToken.Brand.primary)
                                .clipShape(Capsule())
                        }
                    }
                } else {
                    // Pre-workout state
                    Text("Start Workout")
                        .font(.system(size: 17, weight: .semibold))
                        .foregroundColor(ColorsToken.Text.primary)
                    
                    Spacer()
                    
                    Button {
                        dismiss()
                    } label: {
                        Image(systemName: "xmark")
                            .font(.system(size: 17, weight: .medium))
                            .foregroundColor(ColorsToken.Text.secondary)
                    }
                }
            }
            .padding(.horizontal, Space.md)
            .padding(.vertical, Space.sm)
            
            Divider()
        }
        .background(ColorsToken.Background.primary)
        // Name editor alert
        .alert("Workout Name", isPresented: $showingNameEditor) {
            TextField("Name", text: $editingName)
            Button("Save") {
                updateWorkoutName(editingName)
            }
            Button("Cancel", role: .cancel) { }
        }
        // Discard confirmation
        .confirmationDialog("Discard Workout?", isPresented: $showingCancelConfirmation) {
            Button("Discard", role: .destructive) {
                discardWorkout()
            }
            Button("Keep Logging", role: .cancel) { }
        } message: {
            Text("Your progress will not be saved.")
        }
    }
    
    private func formatStartTime(_ date: Date) -> String {
        let formatter = DateFormatter()
        let calendar = Calendar.current
        
        if calendar.isDateInToday(date) {
            formatter.dateFormat = "'Today at' h:mm a"
        } else if calendar.isDateInYesterday(date) {
            formatter.dateFormat = "'Yesterday at' h:mm a"
        } else {
            formatter.dateFormat = "MMM d 'at' h:mm a"
        }
        
        return formatter.string(from: date)
    }
    
    private func updateWorkoutName(_ name: String) {
        guard !name.isEmpty else { return }
        Task {
            // TODO: Update workout name via service
            // For now just update locally
            print("Update workout name to: \(name)")
        }
    }
    
    private func discardWorkout() {
        stopTimer()
        Task {
            // TODO: Call cancelActiveWorkout endpoint
            print("Discarding workout...")
        }
        dismiss()
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
    
    // MARK: - Workout Header
    
    private var workoutHeader: some View {
        Group {
            if let workout = service.workout {
                VStack(spacing: 0) {
                    Text(workout.name ?? "Workout")
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundColor(ColorsToken.Text.primary)
                        .lineLimit(1)
                    
                    Text(formatDuration(elapsedTime))
                        .font(.system(size: 12, weight: .medium).monospacedDigit())
                        .foregroundColor(ColorsToken.Text.secondary)
                }
            } else {
                Text("Start Workout")
                    .font(.system(size: 17, weight: .semibold))
                    .foregroundColor(ColorsToken.Text.primary)
            }
        }
    }
    
    // MARK: - AI Panel Placeholder
    
    private var aiPanelPlaceholder: some View {
        NavigationStack {
            VStack(spacing: Space.xl) {
                Image(systemName: "sparkles")
                    .font(.system(size: 48))
                    .foregroundColor(ColorsToken.Brand.primary)
                
                Text("Copilot")
                    .font(.system(size: 20, weight: .semibold))
                
                Text("AI assistance coming soon")
                    .font(.system(size: 15))
                    .foregroundColor(ColorsToken.Text.secondary)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(ColorsToken.Background.primary)
            .navigationTitle("Copilot")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Done") { showingAIPanel = false }
                }
            }
        }
        .presentationDetents([.medium])
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
    
    // MARK: - Timer
    
    private func startTimer() {
        guard let workout = service.workout else { return }
        elapsedTime = Date().timeIntervalSince(workout.startTime)
        
        timer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { _ in
            Task { @MainActor in
                if let workout = service.workout {
                    elapsedTime = Date().timeIntervalSince(workout.startTime)
                }
            }
        }
    }
    
    private func stopTimer() {
        timer?.invalidate()
        timer = nil
    }
    
    // MARK: - Actions
    
    private func startWorkoutIfNeeded() async {
        guard service.workout == nil else {
            startTimer()
            return
        }
        
        if sourceTemplateId != nil || sourceRoutineId != nil {
            do {
                _ = try await service.startWorkout(
                    name: workoutName,
                    sourceTemplateId: sourceTemplateId,
                    sourceRoutineId: sourceRoutineId
                )
                startTimer()
            } catch {
                print("Failed to start workout: \(error)")
            }
        }
    }
    
    private func startEmptyWorkout() async {
        do {
            _ = try await service.startWorkout(name: "Workout")
            startTimer()
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
    
    var isWeight: Bool {
        if case .weight = self { return true }
        return false
    }
    
    var isReps: Bool {
        if case .reps = self { return true }
        return false
    }
    
    var isRir: Bool {
        if case .rir = self { return true }
        return false
    }
}

// MARK: - Preview

#Preview {
    FocusModeWorkoutScreen()
}
