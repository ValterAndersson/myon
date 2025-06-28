import SwiftUI

struct ActiveWorkoutView: View {
    @StateObject private var workoutManager = ActiveWorkoutManager.shared
    @State private var showingExerciseSelection = false
    @State private var showingCancelAlert = false
    @State private var showingWorkoutSummary = false
    @State private var showingSaveTemplate = false
    @State private var completedWorkoutId: String?
    @State private var isCompletingWorkout = false
    @State private var completionError: Error?
    @State private var showingCompletionError = false
    @Environment(\.presentationMode) var presentationMode
    @State private var workoutJustCompleted = false // Track if workout just completed
    let isExpandedFromMinimized: Bool
    
    init(isExpandedFromMinimized: Bool = false) {
        self.isExpandedFromMinimized = isExpandedFromMinimized
    }
    
    private var hasExercises: Bool {
        workoutManager.activeWorkout?.exercises.isEmpty == false
    }
    
    var body: some View {
        NavigationView {
            VStack(spacing: 0) {
                if let workout = workoutManager.activeWorkout {
                    // Check if workout is completed but summary not yet shown
                    if workout.endTime != nil && !showingWorkoutSummary && workoutJustCompleted {
                        // Workout is completed, trigger summary display
                        Color.clear
                            .onAppear {
                                if let workoutId = completedWorkoutId {
                                    showingWorkoutSummary = true
                                }
                            }
                    } else if workout.endTime == nil {
                        // Active workout in progress - show normal interface
                        // Header with timer and sensor status
                        WorkoutHeaderView(
                            duration: workoutManager.workoutDuration,
                            sensorStatus: workoutManager.sensorStatus,
                            isMinimized: Binding(
                                get: { workoutManager.isMinimized },
                                set: { newValue in 
                                    workoutManager.setMinimized(newValue)
                                    // If minimizing, dismiss this view to show minimized bar
                                    if newValue {
                                        presentationMode.wrappedValue.dismiss()
                                    }
                                }
                            )
                        )
                        
                        // Exercise list
                        if workout.exercises.isEmpty {
                            EmptyWorkoutView(
                                onAddExercise: { showingExerciseSelection = true },
                                onCancel: { showingCancelAlert = true },
                                onComplete: { completeWorkout() },
                                isCompletingWorkout: isCompletingWorkout
                            )
                        } else {
                            ExerciseListScrollView(
                                exercises: workout.exercises,
                                onAddExercise: { showingExerciseSelection = true },
                                onCancel: { showingCancelAlert = true },
                                onComplete: { completeWorkout() },
                                onSaveTemplate: hasExercises ? { showingSaveTemplate = true } : nil,
                                isCompletingWorkout: isCompletingWorkout
                            )
                        }
                    }
                } else {
                    // No active workout - handle navigation
                    VStack {
                        Text("No active workout")
                            .foregroundColor(.secondary)
                    }
                    .onAppear {
                        // Only handle post-workout navigation if not expanded from minimized
                        if !isExpandedFromMinimized {
                            workoutJustCompleted = false // Reset flag
                            handlePostWorkoutNavigation()
                        } else {
                            // Just dismiss if there's no active workout and this was minimized
                            presentationMode.wrappedValue.dismiss()
                        }
                    }
                }
            }
            .navigationTitle("Active Workout")
            .navigationBarTitleDisplayMode(.inline)
        }
        .sheet(isPresented: $showingExerciseSelection) {
            ExerciseSelectionView { exercise in
                workoutManager.addExercise(exercise)
                showingExerciseSelection = false
            }
        }
        .sheet(isPresented: $showingSaveTemplate) {
            if let activeWorkout = workoutManager.activeWorkout {
                SaveTemplateFromWorkoutView(activeWorkout: activeWorkout) { template in
                    // Handle template save - you could save to your template service here
                    print("Template saved: \(template.name)")
                    showingSaveTemplate = false
                }
            }
        }
        .fullScreenCover(isPresented: $showingWorkoutSummary) {
            if let workoutId = completedWorkoutId {
                WorkoutSummaryView(workoutId: workoutId, onDismiss: {
                    // Clear the completed workout data and handle navigation
                    workoutManager.clearCompletedWorkout()
                    showingWorkoutSummary = false
                    workoutJustCompleted = false
                    
                    // Add a small delay to ensure the summary view has dismissed completely
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
                        handlePostWorkoutNavigation()
                    }
                })
            } else {
                Text("Error: No workout ID available")
            }
        }
        .alert("Cancel Workout", isPresented: $showingCancelAlert) {
            Button("Cancel Workout", role: .destructive) {
                workoutManager.cancelWorkout()
                workoutJustCompleted = false // Reset flag for cancel
                handlePostWorkoutNavigation()
            }
            Button("Keep Going", role: .cancel) {}
        } message: {
            Text("Are you sure you want to cancel this workout? All progress will be lost.")
        }
        .alert("Error Completing Workout", isPresented: $showingCompletionError) {
            Button("OK") {
                completionError = nil
            }
            Button("Try Again") {
                completeWorkout()
            }
        } message: {
            Text(completionError?.localizedDescription ?? "Failed to save workout")
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color(.systemBackground))
    }
    
    private func handlePostWorkoutNavigation() {
        // Only handle navigation if summary was shown and dismissed, or if workout was cancelled
        guard !workoutJustCompleted else { return }
        
        guard let destination = workoutManager.navigationDestination else { return }
        
        switch destination {
        case .workouts, .dashboard:
            // Dismiss this view to let parent handle navigation
            presentationMode.wrappedValue.dismiss()
        case .stayInCurrentView:
            // User navigated away, just dismiss to return to their current view
            presentationMode.wrappedValue.dismiss()
        }
        
        // Mark navigation as complete
        workoutManager.handleNavigationComplete()
    }
    
    private func completeWorkout() {
        // Check if we have any exercises and sets
        guard let workout = workoutManager.activeWorkout,
              !workout.exercises.isEmpty else {
            // Show alert that workout needs exercises
            return
        }
        
        // Check if we have at least one set
        let hasAnySets = workout.exercises.contains { !$0.sets.isEmpty }
        guard hasAnySets else {
            // Show alert that workout needs at least one set
            return
        }
        
        isCompletingWorkout = true
        
        Task {
            do {
                let workoutId = try await workoutManager.completeWorkout()
                
                await MainActor.run {
                    isCompletingWorkout = false
                    if let id = workoutId {
                        completedWorkoutId = id
                        workoutJustCompleted = true // Prevent navigation until summary is dismissed
                        showingWorkoutSummary = true
                    } else {
                        completionError = WorkoutError.saveFailed
                        showingCompletionError = true
                    }
                }
            } catch {
                await MainActor.run {
                    isCompletingWorkout = false
                    completionError = error
                    showingCompletionError = true
                }
            }
        }
    }
}

// MARK: - Header View
struct WorkoutHeaderView: View {
    let duration: TimeInterval
    let sensorStatus: SensorStatus
    @Binding var isMinimized: Bool
    @State private var showingTimeEditor = false
    
    var body: some View {
        VStack(spacing: 8) {
            HStack {
                // Timer - now clickable
                Button(action: { showingTimeEditor = true }) {
                    Text(formatDuration(duration))
                        .font(.title2.monospacedDigit())
                        .fontWeight(.semibold)
                        .foregroundColor(.primary)
                }
                .buttonStyle(PlainButtonStyle())
                
                Spacer()
                
                // Minimize/Maximize button
                Button(action: { isMinimized.toggle() }) {
                    Image(systemName: isMinimized ? "arrow.up.left.and.arrow.down.right" : "arrow.down.right.and.arrow.up.left")
                        .foregroundColor(.blue)
                }
            }
            
            // Sensor status
            if !isMinimized {
                SensorStatusView(status: sensorStatus)
            }
        }
        .padding()
        .background(Color(.systemGray6))
        .sheet(isPresented: $showingTimeEditor) {
            WorkoutTimeEditorView()
        }
    }
    
    private func formatDuration(_ duration: TimeInterval) -> String {
        let hours = Int(duration) / 3600
        let minutes = (Int(duration) % 3600) / 60
        let seconds = Int(duration) % 60
        
        if hours > 0 {
            return String(format: "%d:%02d:%02d", hours, minutes, seconds)
        } else {
            return String(format: "%d:%02d", minutes, seconds)
        }
    }
}

// MARK: - Workout Time Editor
struct WorkoutTimeEditorView: View {
    @StateObject private var workoutManager = ActiveWorkoutManager.shared
    @State private var startTime: Date = Date()
    @Environment(\.presentationMode) var presentationMode
    
    var body: some View {
        NavigationView {
            VStack(spacing: 24) {
                Text("Edit Start Time")
                    .font(.title2)
                    .fontWeight(.semibold)
                
                DatePicker("Start Time", selection: $startTime, displayedComponents: [.date, .hourAndMinute])
                    .datePickerStyle(WheelDatePickerStyle())
                    .labelsHidden()
                
                Spacer()
            }
            .padding()
            .navigationTitle("Edit Time")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Cancel") {
                        presentationMode.wrappedValue.dismiss()
                    }
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Save") {
                        workoutManager.updateStartTime(startTime)
                        presentationMode.wrappedValue.dismiss()
                    }
                }
            }
        }
        .onAppear {
            startTime = workoutManager.activeWorkout?.startTime ?? Date()
        }
    }
}

// MARK: - Sensor Status View
struct SensorStatusView: View {
    let status: SensorStatus
    
    var body: some View {
        HStack {
            Image(systemName: sensorIcon)
                .foregroundColor(sensorColor)
            
            Text(sensorText)
                .font(.caption)
                .foregroundColor(sensorColor)
            
            Spacer()
        }
    }
    
    private var sensorIcon: String {
        switch status {
        case .noSensors:
            return "sensor.tag.radiowaves.forward.fill"
        case .sensorsAvailable:
            return "sensor.tag.radiowaves.forward"
        case .sensorsConnected:
            return "sensor.tag.radiowaves.forward.fill"
        case .sensorsDisconnected:
            return "sensor.tag.radiowaves.forward"
        }
    }
    
    private var sensorColor: Color {
        switch status {
        case .noSensors:
            return .gray
        case .sensorsAvailable:
            return .orange
        case .sensorsConnected:
            return .green
        case .sensorsDisconnected:
            return .red
        }
    }
    
    private var sensorText: String {
        switch status {
        case .noSensors:
            return "No sensors available for this workout"
        case .sensorsAvailable(let count):
            return "\(count) sensor(s) available"
        case .sensorsConnected(let count):
            return "\(count) sensor(s) connected"
        case .sensorsDisconnected:
            return "Sensors disconnected"
        }
    }
}

// MARK: - Empty Workout View
struct EmptyWorkoutView: View {
    let onAddExercise: () -> Void
    let onCancel: () -> Void
    let onComplete: () -> Void
    let isCompletingWorkout: Bool
    
    var body: some View {
        VStack(spacing: 20) {
            Spacer()
            
            Image(systemName: "dumbbell")
                .font(.system(size: 60))
                .foregroundColor(.gray)
            
            Text("No Exercises Added")
                .font(.title2)
                .fontWeight(.semibold)
            
            Text("Add exercises to start your workout")
                .font(.subheadline)
                .foregroundColor(.secondary)
            
            Button(action: onAddExercise) {
                Label("Add Exercise", systemImage: "plus")
                    .padding()
                    .background(Color.blue)
                    .foregroundColor(.white)
                    .cornerRadius(12)
            }
            
            Spacer()
            
            // Controls at bottom 
            CompactWorkoutControlsView(
                onAddExercise: onAddExercise,
                onCancel: onCancel,
                onComplete: onComplete,
                onSaveTemplate: nil, // No exercises to save as template
                isCompletingWorkout: isCompletingWorkout
            )
            .padding(.bottom, 40)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

// MARK: - Exercise List Scroll View
struct ExerciseListScrollView: View {
    let exercises: [ActiveExercise]
    let onAddExercise: () -> Void
    let onCancel: () -> Void
    let onComplete: () -> Void
    let onSaveTemplate: (() -> Void)?
    let isCompletingWorkout: Bool
    @State private var isReorderMode = false
    @StateObject private var workoutManager = ActiveWorkoutManager.shared
    
    var body: some View {
        VStack(spacing: 0) {
            // Reorder mode toggle
            if !exercises.isEmpty {
                HStack {
                    Text("\(exercises.count) exercises")
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                    
                    Spacer()
                    
                    Button(action: { 
                        isReorderMode.toggle()
                    }) {
                        HStack {
                            Image(systemName: isReorderMode ? "checkmark" : "arrow.up.arrow.down")
                            Text(isReorderMode ? "Done" : "Reorder")
                        }
                        .font(.caption)
                        .foregroundColor(.blue)
                    }
                }
                .padding(.horizontal)
                .padding(.top, 8)
            }
            
            if isReorderMode {
                // Use List for reordering since drag and drop is complex
                List {
                    ForEach(Array(exercises.enumerated()), id: \.element.id) { index, exercise in
                        HStack {
                            Image(systemName: "line.3.horizontal")
                                .foregroundColor(.gray)
                            Text(exercise.name.capitalized)
                                .font(.headline)
                            Spacer()
                            Button(action: {
                                workoutManager.removeExercise(id: exercise.id)
                            }) {
                                Image(systemName: "trash")
                                    .foregroundColor(.red)
                            }
                        }
                        .padding(.vertical, 4)
                    }
                    .onMove { fromOffsets, toOffset in
                        workoutManager.moveExercise(fromOffsets: fromOffsets, toOffset: toOffset)
                    }
                }
                .listStyle(PlainListStyle())
            } else {
                ScrollView {
                    LazyVStack(spacing: 16) {
                        ForEach(exercises) { exercise in
                            ActiveExerciseCard(
                                exercise: exercise,
                                isReorderMode: false,
                                onMove: { _, _ in },
                                onDelete: { _ in }
                            )
                        }
                        
                        // Controls at bottom of content (not sticky)
                        CompactWorkoutControlsView(
                            onAddExercise: onAddExercise,
                            onCancel: onCancel,
                            onComplete: onComplete,
                            onSaveTemplate: onSaveTemplate,
                            isCompletingWorkout: isCompletingWorkout
                        )
                        .padding(.top, 32)
                        .padding(.bottom, 40) // Extra bottom padding for comfortable scrolling
                    }
                    .padding()
                }
                .scrollDismissesKeyboard(.interactively)
                .onTapGesture {
                    // Dismiss keyboard when tapping in scroll view
                    UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil)
                }
                .toolbar {
                    ToolbarItemGroup(placement: .keyboard) {
                        Spacer()
                        Button("Done") {
                            UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil)
                        }
                    }
                }
            }
        }
    }
}

// MARK: - Active Exercise Card
struct ActiveExerciseCard: View {
    let exercise: ActiveExercise
    let isReorderMode: Bool
    let onMove: (IndexSet, Int) -> Void
    let onDelete: (ActiveExercise) -> Void
    @StateObject private var workoutManager = ActiveWorkoutManager.shared
    @StateObject private var exercisesViewModel = ExercisesViewModel()
    @State private var showingExerciseDetail = false
    @State private var configurableSets: [ConfigurableSet] = []
    
    // Default initializer for backward compatibility
    init(exercise: ActiveExercise, isReorderMode: Bool = false, onMove: @escaping (IndexSet, Int) -> Void = { _, _ in }, onDelete: @escaping (ActiveExercise) -> Void = { _ in }) {
        self.exercise = exercise
        self.isReorderMode = isReorderMode
        self.onMove = onMove
        self.onDelete = onDelete
    }
    
    var body: some View {
        CardContainer {
        VStack(alignment: .leading, spacing: 12) {
                // Exercise header with reorder handle
            HStack {
                    if isReorderMode {
                        Image(systemName: "line.3.horizontal")
                            .foregroundColor(.gray)
                            .font(.title2)
                    }
                    
                Button(action: { 
                    loadExerciseAndShowDetail()
                }) {
                    Text(exercise.name.capitalized)
                        .font(.headline)
                        .textCase(.none)
                        .foregroundColor(.primary)
                        .multilineTextAlignment(.leading)
                }
                .buttonStyle(PlainButtonStyle())
                    .disabled(isReorderMode)
                
                Spacer()
                
                    if isReorderMode {
                        Button(action: { onDelete(exercise) }) {
                            Image(systemName: "trash")
                                .foregroundColor(.red)
                        }
                    } else {
                Menu {
                    Button("Add Set", systemImage: "plus") {
                        workoutManager.addSet(toExerciseId: exercise.id)
                    }
                    Button("Remove Exercise", systemImage: "trash", role: .destructive) {
                        workoutManager.removeExercise(id: exercise.id)
                    }
                } label: {
                    Image(systemName: "ellipsis")
                        .foregroundColor(.gray)
                        }
                    }
                }
                
                if !isReorderMode {
                    // Sets section
                    VStack(alignment: .leading, spacing: 8) {
                    HStack {
                            Text("Sets")
                                .font(.subheadline)
                                .fontWeight(.medium)
                            
                            Spacer()
                            
                            Button(action: { 
                                workoutManager.addSet(toExerciseId: exercise.id)
                            }) {
                                Image(systemName: "plus.circle.fill")
                                    .foregroundColor(.blue)
                            }
                        }
                        
                        if exercise.sets.isEmpty {
                            Text("No sets added")
                            .font(.caption)
                            .foregroundColor(.secondary)
                                .padding(.vertical, 8)
                        } else {
                            VStack(spacing: 8) {
                                // Set rows - no header needed since each has labels
                    ForEach(Array(exercise.sets.enumerated()), id: \.element.id) { index, set in
                        ActiveSetRow(
                            setNumber: index + 1,
                            set: set,
                            exerciseId: exercise.id
                        )
                    }
                }
            }
                    }
                }
            }
        }
        .opacity(isReorderMode ? 0.8 : 1.0)
        .onAppear {
            syncSets()
        }
        .onChange(of: exercise.sets) {
            syncSets()
        }
        .sheet(isPresented: $showingExerciseDetail) {
            if let exerciseData = getExerciseData(for: exercise.exerciseId) {
                NavigationView {
                    ExerciseDetailView(exercise: exerciseData)
                        .toolbar {
                            ToolbarItem(placement: .navigationBarTrailing) {
                                Button("Done") {
                                    showingExerciseDetail = false
                                }
                            }
                        }
                }
            } else {
                VStack {
                    Text("Exercise details not available")
                        .font(.headline)
                    Text("Unable to load exercise information")
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                    
                    Button("Close") {
                        showingExerciseDetail = false
                    }
                    .padding()
                }
                .padding()
            }
        }
    }
    
    private func syncSets() {
        configurableSets = exercise.sets.map { ConfigurableSet(from: $0) }
    }
    
    private func loadExerciseAndShowDetail() {
        Task {
            if exercisesViewModel.exercises.isEmpty {
                await exercisesViewModel.loadExercises()
            }
            await MainActor.run {
                showingExerciseDetail = true
            }
        }
    }
    
    private func getExerciseData(for exerciseId: String) -> Exercise? {
        return exercisesViewModel.exercises.first { $0.id == exerciseId }
    }
}

// MARK: - Active Set Row
struct ActiveSetRow: View {
    let setNumber: Int
    let set: ActiveSet
    let exerciseId: String
    @StateObject private var workoutManager = ActiveWorkoutManager.shared
    @State private var localSet: ActiveSet
    @State private var showingTypeMenu = false
    @State private var showingRIRPicker = false
    @State private var dragOffset: CGFloat = 0
    @State private var hasTriggeredHaptic = false
    
    init(setNumber: Int, set: ActiveSet, exerciseId: String) {
        self.setNumber = setNumber
        self.set = set
        self.exerciseId = exerciseId
        self._localSet = State(initialValue: set)
    }
    
    var body: some View {
        ZStack {
            // Red background that's only shown when swiping (not for completed sets)
            if dragOffset < 0 {
                HStack {
                    Spacer()
                    HStack(spacing: 8) {
                        Image(systemName: "trash")
                            .font(.title2)
                            .foregroundColor(.white)
                        Text("Delete")
                            .font(.headline)
                            .foregroundColor(.white)
                    }
                    .padding(.trailing, 20)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(Color.red)
                .cornerRadius(12)
            }
            
            // Main content that moves over the red background
            HStack(spacing: 12) {
                // Set number with type
                VStack(spacing: 2) {
                    Text("\(setNumber)")
                        .font(.headline)
                        .fontWeight(.semibold)
                    
                    Button(action: { showingTypeMenu = true }) {
                        Text(setTypeAbbreviation)
                            .font(.caption2)
                            .foregroundColor(.secondary)
                            .padding(.horizontal, 4)
                            .padding(.vertical, 1)
                            .background(Color(.systemGray5))
                            .cornerRadius(3)
                    }
                }
                .frame(width: 35)
                .opacity(localSet.isCompleted ? 0.6 : 1.0)
                
                // Weight input - traditional text field
                VStack(spacing: 2) {
                    Text("kg")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                    
                    TextField("0", value: $localSet.weight, format: .number.precision(.fractionLength(0...1)))
                        .textFieldStyle(RoundedBorderTextFieldStyle())
                        .frame(width: 60)
                        .keyboardType(.decimalPad)
                        .multilineTextAlignment(.center)
                        .font(.system(.body, design: .monospaced))
                        .submitLabel(.done)
                        .onSubmit {
                            // Dismiss keyboard when done
                            UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil)
                        }
                        .onChange(of: localSet.weight) { 
                            updateSet()
                        }
                        .opacity(localSet.isCompleted ? 0.6 : 1.0)
                        .disabled(localSet.isCompleted)
                }
                
                // Reps input - traditional text field
                VStack(spacing: 2) {
                    Text("reps")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                    
                    TextField("0", value: $localSet.reps, format: .number)
                        .textFieldStyle(RoundedBorderTextFieldStyle())
                        .frame(width: 50)
                        .keyboardType(.numberPad)
                        .multilineTextAlignment(.center)
                        .font(.system(.body, design: .monospaced))
                        .submitLabel(.done)
                        .onSubmit {
                            // Dismiss keyboard when done
                            UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil)
                        }
                        .onChange(of: localSet.reps) { updateSet() }
                        .opacity(localSet.isCompleted ? 0.6 : 1.0)
                        .disabled(localSet.isCompleted)
                }
                
                // RIR - single field
                VStack(spacing: 2) {
                    Text("RIR")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                    
                    Button(action: { showingRIRPicker = true }) {
                        Text("\(localSet.rir)")
                            .font(.system(.body, design: .monospaced))
                            .fontWeight(.medium)
                            .frame(width: 40, height: 31)
                            .background(Color(.systemGray6))
                            .cornerRadius(6)
                            .overlay(
                                RoundedRectangle(cornerRadius: 6)
                                    .stroke(Color(.systemGray4), lineWidth: 1)
                            )
                    }
                    .buttonStyle(PlainButtonStyle())
                    .disabled(localSet.isCompleted)
                    .opacity(localSet.isCompleted ? 0.6 : 1.0)
                }
                
                Spacer()
                
                // Completion button only
                Button(action: {
                    let impactFeedback = UIImpactFeedbackGenerator(style: .medium)
                    impactFeedback.impactOccurred()
                    localSet.isCompleted.toggle()
                    updateSet()
                }) {
                    Image(systemName: localSet.isCompleted ? "checkmark.circle.fill" : "circle")
                        .font(.title2)
                        .foregroundColor(localSet.isCompleted ? .green : .blue)
                        .frame(width: 44, height: 44) // Larger tap target
                        .contentShape(Rectangle()) // Ensure entire area is tappable
                }
                .buttonStyle(PlainButtonStyle())
            }
            .padding(12)
            .background(
                RoundedRectangle(cornerRadius: 12)
                    .fill(localSet.isCompleted ? Color.green.opacity(0.05) : Color(.systemGray6))
                    .stroke(localSet.isCompleted ? Color.green.opacity(0.3) : Color.clear, lineWidth: 1)
            )
            .offset(x: dragOffset)
            .gesture(
                DragGesture(minimumDistance: 20)
                    .onChanged { value in
                        let translation = value.translation.width
                        if translation < 0 { // Only allow left swipe
                            withAnimation(.interactiveSpring(response: 0.3, dampingFraction: 1.0)) {
                                dragOffset = max(translation, -120) // Limit max swipe
                            }
                            
                            // Haptic feedback at halfway point (now -100 instead of -80)
                            if dragOffset <= -100 && !hasTriggeredHaptic {
                                let impactFeedback = UIImpactFeedbackGenerator(style: .medium)
                                impactFeedback.impactOccurred()
                                hasTriggeredHaptic = true
                            } else if dragOffset > -100 {
                                hasTriggeredHaptic = false
                            }
                        }
                    }
                    .onEnded { value in
                        // Require swipe velocity or distance for deletion
                        let translation = value.translation.width
                        let velocity = value.velocity.width
                        
                        // Delete if swiped far enough AND with sufficient velocity, or if swiped very far
                        if (dragOffset <= -100 && velocity < -300) || dragOffset <= -110 {
                            // Auto-delete with haptic after a small delay to show the visual
                            let impactFeedback = UIImpactFeedbackGenerator(style: .heavy)
                            impactFeedback.impactOccurred()
                            
                            // Small delay to let user see the full delete state
                            DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
                                workoutManager.removeSet(exerciseId: exerciseId, setId: localSet.id)
                            }
                        } else {
                            // Snap back
                            withAnimation(.easeOut(duration: 0.3)) {
                                dragOffset = 0
                            }
                        }
                        hasTriggeredHaptic = false
                    }
            )
        }
        .onTapGesture {
            // Tap anywhere to dismiss swipe state and keyboard
            if dragOffset != 0 {
                withAnimation(.easeOut(duration: 0.3)) {
                    dragOffset = 0
                }
            }
            // Also dismiss keyboard if it's open
            UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil)
        }

        .onAppear {
            localSet = set
        }
        .onChange(of: set) {
            localSet = set
            // Reset swipe state when set changes
            dragOffset = 0
            hasTriggeredHaptic = false
        }
        .sheet(isPresented: $showingTypeMenu) {
            SetTypeSelector(selectedType: $localSet.type) {
                updateSet()
            }
        }
        .sheet(isPresented: $showingRIRPicker) {
            QuickRIRPicker(selectedRIR: $localSet.rir) {
                updateSet()
            }
        }
    }
    
    private var setTypeAbbreviation: String {
        switch localSet.type {
        case "Working Set": return "W"
        case "Warm-up": return "WU"
        case "Drop Set": return "D"
        case "Failure Set": return "F"
        default: return "W"
        }
    }
    
    private func updateSet() {
        workoutManager.updateSet(exerciseId: exerciseId, set: localSet)
    }
}

// MARK: - Set Type Selector
struct SetTypeSelector: View {
    @Binding var selectedType: String
    let onSelection: () -> Void
    @Environment(\.presentationMode) var presentationMode
    
    private let setTypes = ["Working Set", "Warm-up", "Drop Set", "Failure Set"]
    
    var body: some View {
        NavigationView {
            List {
                ForEach(setTypes, id: \.self) { type in
                    Button(action: {
                        selectedType = type
                        onSelection()
                        presentationMode.wrappedValue.dismiss()
                    }) {
                        HStack {
                            Text(type)
                                .foregroundColor(.primary)
                            Spacer()
                            if selectedType == type {
                                Image(systemName: "checkmark")
                                    .foregroundColor(.blue)
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

// MARK: - Quick RIR Picker
struct QuickRIRPicker: View {
    @Binding var selectedRIR: Int
    let onSelection: () -> Void
    @Environment(\.presentationMode) var presentationMode
    
    var body: some View {
        NavigationView {
            VStack(spacing: 24) {
                Text("RIR (Reps in Reserve)")
                    .font(.title3)
                    .fontWeight(.semibold)
                
                Text("How many more reps could you do?")
                    .font(.subheadline)
                    .foregroundColor(.secondary)
                
                // Horizontal selection
                HStack(spacing: 20) {
                    ForEach(0...4, id: \.self) { rir in
                        Button(action: {
                            selectedRIR = rir
                            onSelection()
                            presentationMode.wrappedValue.dismiss()
                        }) {
                            VStack(spacing: 8) {
                                Text("\(rir)")
                                    .font(.title)
                                    .fontWeight(.bold)
                                    .frame(width: 50, height: 50)
                                    .background(selectedRIR == rir ? Color.blue : Color(.systemGray5))
                                    .foregroundColor(selectedRIR == rir ? .white : .primary)
                                    .cornerRadius(25)
                                
                                Text(rirLabel(for: rir))
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                            }
                        }
                        .buttonStyle(PlainButtonStyle())
                    }
                }
                .padding()
                
                Spacer()
            }
            .padding()
            .navigationTitle("")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Done") {
                        presentationMode.wrappedValue.dismiss()
                    }
                }
            }
        }
        .presentationDetents([.height(280)])
        .presentationDragIndicator(.visible)
    }
    
    private func rirLabel(for rir: Int) -> String {
        switch rir {
        case 0: return "Failure"
        case 1: return "Very Hard"
        case 2: return "Hard"
        case 3: return "Moderate"
        case 4: return "Easy"
        default: return ""
        }
    }
}

// MARK: - Compact Workout Controls
struct CompactWorkoutControlsView: View {
    let onAddExercise: () -> Void
    let onCancel: () -> Void
    let onComplete: () -> Void
    let onSaveTemplate: (() -> Void)?
    let isCompletingWorkout: Bool
    
    var body: some View {
        VStack(spacing: 12) {
            // Primary row with main actions
            HStack(spacing: 12) {
                Button(action: onAddExercise) {
                    Image(systemName: "plus")
                    Text("Add Exercise")
                }
                .buttonStyle(CompactSecondaryButtonStyle())
                .disabled(isCompletingWorkout)
                
                Button(action: onCancel) {
                    Text("Cancel")
                }
                .buttonStyle(CompactDestructiveButtonStyle())
                .disabled(isCompletingWorkout)
                
                Button(action: onComplete) {
                    HStack(spacing: 4) {
                        if isCompletingWorkout {
                            ProgressView()
                                .scaleEffect(0.7)
                            Text("Saving...")
                        } else {
                            Text("Finish")
                        }
                    }
                }
                .buttonStyle(CompactPrimaryButtonStyle())
                .disabled(isCompletingWorkout)
            }
            
            // Save as Template button (if available and workout has exercises)
            if let onSaveTemplate = onSaveTemplate {
                Button(action: onSaveTemplate) {
                    HStack(spacing: 4) {
                        Image(systemName: "square.and.arrow.down")
                        Text("Save as Template")
                    }
                }
                .buttonStyle(CompactSecondaryButtonStyle())
                .disabled(isCompletingWorkout)
            }
        }
    }
}

// MARK: - Compact Button Styles
struct CompactPrimaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(.subheadline, weight: .semibold))
            .foregroundColor(.white)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 10)
            .padding(.horizontal, 16)
            .background(
                RoundedRectangle(cornerRadius: 8)
                    .fill(Color.blue)
                    .opacity(configuration.isPressed ? 0.8 : 1.0)
            )
    }
}

struct CompactSecondaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(.subheadline, weight: .medium))
            .foregroundColor(.blue)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 10)
            .padding(.horizontal, 16)
            .background(
                RoundedRectangle(cornerRadius: 8)
                    .fill(Color(.systemGray6))
                    .opacity(configuration.isPressed ? 0.8 : 1.0)
            )
    }
}

struct CompactDestructiveButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(.subheadline, weight: .medium))
            .foregroundColor(.red)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 10)
            .padding(.horizontal, 16)
            .background(
                RoundedRectangle(cornerRadius: 8)
                    .fill(Color(.systemGray6))
                    .opacity(configuration.isPressed ? 0.8 : 1.0)
            )
    }
}

#Preview {
    ActiveWorkoutView(isExpandedFromMinimized: false)
} 