import SwiftUI

/// A coaching-first workout plan display.
/// Designed to feel like an interactive coaching artifact, not a card embedded in chat.
public struct SessionPlanCard: View {
    private let model: CanvasCardModel
    @State private var editableExercises: [PlanExercise] = []
    @State private var exerciseForDetail: PlanExercise? = nil
    @State private var exerciseForEdit: (exercise: PlanExercise, index: Int)? = nil
    @State private var showingActionsSheet = false
    @State private var expandedExerciseId: String? = nil  // Track which exercise is expanded
    @State private var setEditContext: (exerciseIndex: Int, setIndex: Int)? = nil  // Track which set is being edited
    @State private var warmupCollapsed: [String: Bool] = [:]  // Track warm-up collapse state per exercise
    
    // Grid selection state for spreadsheet-style editing
    @State private var selectedCell: GridCellField? = nil
    @State private var editScope: EditScope = .allWorking
    
    @Environment(\.cardActionHandler) private var handleAction
    
    public init(model: CanvasCardModel) {
        self.model = model
    }
    
    // MARK: - Computed
    
    private var totalSets: Int {
        editableExercises.reduce(0) { $0 + $1.setCount }
    }
    
    private var estimatedMinutes: Int {
        // Rough estimate: 2-3 min per set
        max(20, totalSets * 2 + 5)
    }
    
    private var focusSummary: String? {
        // Derive focus from primary muscles
        let muscles = editableExercises.compactMap { $0.primaryMuscles }.flatMap { $0 }
        let counts = Dictionary(grouping: muscles, by: { $0 }).mapValues { $0.count }
        if let top = counts.max(by: { $0.value < $1.value })?.key {
            return "\(top.capitalized) biased"
        }
        return nil
    }
    
    private var statusText: String {
        switch model.status {
        case .proposed: return "Proposed"
        case .accepted: return "Ready"
        case .active: return "In Progress"
        case .completed: return "Done"
        case .rejected: return "Dismissed"
        case .expired: return "Expired"
        }
    }
    
    private var statusColor: Color {
        switch model.status {
        case .proposed: return ColorsToken.Brand.primary
        case .accepted, .completed: return ColorsToken.State.success
        case .active: return ColorsToken.State.warning
        case .rejected, .expired: return ColorsToken.Text.secondary
        }
    }
    
    // MARK: - Body
    
    public var body: some View {
        VStack(alignment: .leading, spacing: Space.md) {
            // Title with inline status
            titleRow
            
            // Summary line
            summaryLine
            
            // Iteration actions (visible, not hidden in menu)
            if model.status == .proposed {
                iterationActions
            }
            
            // Divider
            Rectangle()
                .fill(ColorsToken.Border.subtle)
                .frame(height: 1)
            
            // Exercise list with swipe actions
            exerciseList
            
            // Primary action
            if model.status == .proposed {
                acceptButton
            }
        }
        .padding(Space.md)
        .background(ColorsToken.Surface.card)
        .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.large))
        .shadow(color: Color.black.opacity(0.08), radius: 8, x: 0, y: 2)  // Depth instead of accent border
        .onAppear {
            if case .sessionPlan(let exercises) = model.data {
                editableExercises = exercises
            }
        }
        .onChange(of: model.data) { newData in
            if case .sessionPlan(let exercises) = newData {
                editableExercises = exercises
            }
        }
        .sheet(item: $exerciseForDetail) { exercise in
            ExerciseDetailSheet(
                exerciseId: exercise.exerciseId,
                exerciseName: exercise.name,
                onDismiss: { exerciseForDetail = nil }
            )
        }
        .sheet(isPresented: Binding(
            get: { exerciseForEdit != nil },
            set: { if !$0 { exerciseForEdit = nil } }
        )) {
            if let edit = exerciseForEdit {
                editSheet(exercise: edit.exercise, index: edit.index)
            }
        }
        .confirmationDialog("Plan Actions", isPresented: $showingActionsSheet, titleVisibility: .hidden) {
            planActionsSheet
        }
        .sheet(isPresented: Binding(
            get: { setEditContext != nil },
            set: { if !$0 { setEditContext = nil } }
        )) {
            if let ctx = setEditContext,
               let exercise = editableExercises[safe: ctx.exerciseIndex],
               let set = exercise.sets[safe: ctx.setIndex] {
                SetEditSheet(
                    exerciseName: exercise.name,
                    setIndex: ctx.setIndex,
                    set: set,
                    isWarmup: set.isWarmup,
                    onSave: { updatedSet in
                        editableExercises[ctx.exerciseIndex].sets[ctx.setIndex] = updatedSet
                        setEditContext = nil
                    },
                    onDelete: {
                        editableExercises[ctx.exerciseIndex].sets.remove(at: ctx.setIndex)
                        setEditContext = nil
                    },
                    onDismiss: { setEditContext = nil }
                )
            }
        }
    }
    
    // MARK: - Title Row
    
    private var titleRow: some View {
        HStack(alignment: .center, spacing: Space.sm) {
            // Title
            Text(model.title ?? "Workout")
                .font(.system(size: 18, weight: .semibold))
                .foregroundColor(ColorsToken.Text.primary)
            
            // Status pill
            Text(statusText)
                .font(.system(size: 11, weight: .medium))
                .foregroundColor(statusColor)
                .padding(.horizontal, 8)
                .padding(.vertical, 3)
                .background(statusColor.opacity(0.12))
                .clipShape(Capsule())
            
            Spacer()
            
            // Minimal overflow (only for destructive/rare actions)
            Button { showingActionsSheet = true } label: {
                Image(systemName: "ellipsis")
                    .font(.system(size: 14, weight: .medium))
                    .foregroundColor(ColorsToken.Text.secondary)
                    .frame(width: 28, height: 28)
            }
            .buttonStyle(PlainButtonStyle())
        }
    }
    
    // MARK: - Summary Line
    
    private var summaryLine: some View {
        HStack(spacing: Space.sm) {
            summaryPill("\(editableExercises.count) exercises")
            summaryPill("\(totalSets) sets")
            summaryPill("~\(estimatedMinutes) min")
            if let focus = focusSummary {
                summaryPill(focus)
            }
        }
    }
    
    private func summaryPill(_ text: String) -> some View {
        Text(text)
            .font(.system(size: 12, weight: .medium))
            .foregroundColor(ColorsToken.Text.secondary)
    }
    
    // MARK: - Iteration Actions (visible, not in menu)
    
    private var iterationActions: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: Space.sm) {
                iterationPill("Shorter", icon: "minus.circle") {
                    fireAdjustment("Make this session shorter - reduce total sets or exercises")
                }
                iterationPill("Harder", icon: "flame") {
                    fireAdjustment("Make this session more challenging - increase intensity or volume")
                }
                iterationPill("Swap Focus", icon: "arrow.triangle.2.circlepath") {
                    fireAdjustment("Change the muscle focus of this workout")
                }
                iterationPill("Regenerate", icon: "sparkles") {
                    fireAdjustment("Regenerate this workout plan with different exercises")
                }
            }
        }
    }
    
    private func iterationPill(_ label: String, icon: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 4) {
                Image(systemName: icon)
                    .font(.system(size: 11))
                Text(label)
                    .font(.system(size: 12, weight: .medium))
            }
            .foregroundColor(ColorsToken.Text.primary)
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(ColorsToken.Background.secondary)
            .clipShape(Capsule())
        }
        .buttonStyle(PlainButtonStyle())
    }
    
    // MARK: - Exercise List (with expand/collapse)
    
    private var exerciseList: some View {
        VStack(spacing: 0) {
            ForEach(editableExercises.indices, id: \.self) { index in
                let exercise = editableExercises[index]
                let isExpanded = expandedExerciseId == exercise.id
                
                VStack(spacing: 0) {
                    // Exercise header row (always visible)
                    exerciseHeaderRow(exercise: exercise, index: index, isExpanded: isExpanded)
                    
                    // Expanded: show sets inline
                    if isExpanded {
                        expandedSetsView(exercise: exercise, index: index)
                    }
                }
                
                if index < editableExercises.count - 1 {
                    Rectangle()
                        .fill(ColorsToken.Border.subtle.opacity(0.5))
                        .frame(height: 1)
                        .padding(.leading, Space.md)
                }
            }
        }
    }
    
    private func exerciseHeaderRow(exercise: PlanExercise, index: Int, isExpanded: Bool) -> some View {
        Button {
            withAnimation(.easeOut(duration: 0.2)) {
                expandedExerciseId = isExpanded ? nil : exercise.id
            }
        } label: {
            HStack(spacing: Space.sm) {
                // Exercise name and prescription
                VStack(alignment: .leading, spacing: 2) {
                    Text(exercise.name)
                        .font(.system(size: 15, weight: .medium))
                        .foregroundColor(ColorsToken.Text.primary)
                    
                    // Summary line
                    Text(exercise.summaryLine)
                        .font(.system(size: 13))
                        .foregroundColor(ColorsToken.Text.secondary)
                }
                
                Spacer()
                
                // Expand/collapse chevron
                Image(systemName: isExpanded ? "chevron.down" : "chevron.right")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(ColorsToken.Text.secondary.opacity(0.5))
            }
            .padding(.vertical, 12)
            .padding(.horizontal, Space.sm)
            .background(ColorsToken.Surface.card)
        }
        .buttonStyle(PlainButtonStyle())
    }
    
    private func expandedSetsView(exercise: PlanExercise, index: Int) -> some View {
        VStack(spacing: 0) {
            // Coach actions row at top (swap options for this exercise)
            coachActionsRow(exercise: exercise, index: index)
            
            // Use new SetGridView for spreadsheet-style editing
            // SetGridView now includes inline editing dock directly under selected row
            SetGridView(
                sets: Binding(
                    get: { editableExercises[safe: index]?.sets ?? [] },
                    set: { newSets in
                        if editableExercises.indices.contains(index) {
                            editableExercises[index].sets = newSets
                        }
                    }
                ),
                selectedCell: $selectedCell,
                exerciseName: exercise.name,
                warmupCollapsed: warmupCollapsed[exercise.id] ?? true,
                isPlanningMode: model.status == .proposed || model.status == .accepted,  // Planning mode for non-active workouts
                onWarmupToggle: {
                    warmupCollapsed[exercise.id] = !(warmupCollapsed[exercise.id] ?? true)
                },
                onAddSet: { setType in
                    if let lastSet = editableExercises[safe: index]?.sets.last {
                        let newSet = PlanSet(type: setType, reps: setType == .warmup ? 10 : lastSet.reps, weight: lastSet.weight, rir: setType == .warmup ? nil : lastSet.rir)
                        editableExercises[safe: index]?.sets.append(newSet)
                    } else {
                        let newSet = PlanSet(type: setType, reps: setType == .warmup ? 10 : 8, weight: nil, rir: setType == .warmup ? nil : 2)
                        editableExercises[safe: index]?.sets.append(newSet)
                    }
                },
                onDeleteSet: { setIdx in
                    if editableExercises.indices.contains(index), editableExercises[index].sets.indices.contains(setIdx) {
                        editableExercises[index].sets.remove(at: setIdx)
                        selectedCell = nil
                    }
                },
                onUndoDelete: nil  // TODO: Implement undo toast
            )
        }
        .background(ColorsToken.Background.secondary.opacity(0.3))
    }
    
    private func coachActionsRow(exercise: PlanExercise, index: Int) -> some View {
        HStack(spacing: Space.sm) {
            // Adjust dropdown with descriptive swap options
            Menu {
                Button {
                    fireSwap(exercise: exercise, reason: "same_muscles")
                } label: {
                    Label("Same muscle, different equipment", systemImage: "figure.strengthtraining.traditional")
                }
                
                Button {
                    fireSwap(exercise: exercise, reason: "same_equipment")
                } label: {
                    Label("Same equipment, different angle", systemImage: "dumbbell")
                }
                
                Button {
                    fireSwap(exercise: exercise, reason: "different_angle")
                } label: {
                    Label("Different movement pattern", systemImage: "arrow.triangle.branch")
                }
                
                Button {
                    fireSwap(exercise: exercise, reason: "ai_suggestion")
                } label: {
                    Label("Coach's pick", systemImage: "sparkles")
                }
            } label: {
                HStack(spacing: 4) {
                    Image(systemName: "arrow.left.arrow.right")
                        .font(.system(size: 11))
                    Text("Swap")
                        .font(.system(size: 12, weight: .medium))
                    Image(systemName: "chevron.down")
                        .font(.system(size: 8))
                }
                .foregroundColor(ColorsToken.Brand.primary)
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .background(ColorsToken.Brand.primary.opacity(0.1))
                .clipShape(Capsule())
            }
            
            // Exercise Info button (same style as swap)
            Button {
                exerciseForDetail = exercise
            } label: {
                HStack(spacing: 4) {
                    Image(systemName: "info.circle")
                        .font(.system(size: 11))
                    Text("Info")
                        .font(.system(size: 12, weight: .medium))
                }
                .foregroundColor(ColorsToken.Text.secondary)
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .background(ColorsToken.Background.secondary)
                .clipShape(Capsule())
            }
            .buttonStyle(PlainButtonStyle())
            
            // Remove Exercise button (same height as others)
            Button {
                removeExercise(at: index)
            } label: {
                HStack(spacing: 4) {
                    Image(systemName: "trash")
                        .font(.system(size: 11))
                    Text("Remove")
                        .font(.system(size: 12, weight: .medium))
                }
                .foregroundColor(ColorsToken.State.error.opacity(0.8))
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .background(ColorsToken.State.error.opacity(0.08))
                .clipShape(Capsule())
            }
            .buttonStyle(PlainButtonStyle())
            
            Spacer()
        }
        .padding(.horizontal, Space.md)
        .padding(.vertical, Space.xs)
    }
    
    private func isCellInExercise(_ cell: GridCellField, exerciseIndex: Int) -> Bool {
        guard let exercise = editableExercises[safe: exerciseIndex] else { return false }
        // Check if the selected set belongs to this exercise
        return exercise.sets.contains { $0.id == cell.setId }
    }
    
    private func removeExercise(at index: Int) {
        withAnimation(.easeOut(duration: 0.2)) {
            editableExercises.remove(at: index)
        }
    }
    
    // MARK: - Action Buttons (Save as Template + Start Workout)
    
    private var acceptButton: some View {
        HStack(spacing: Space.sm) {
            // Save as Template (Secondary)
            Button {
                let action = CardAction(kind: "save_as_template", label: "Save as Template", style: .secondary, payload: serializePlan())
                handleAction(action, model)
            } label: {
                HStack(spacing: 6) {
                    Image(systemName: "square.and.arrow.down")
                        .font(.system(size: 13, weight: .medium))
                    Text("Save Template")
                        .font(.system(size: 14, weight: .semibold))
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 12)
                .foregroundColor(ColorsToken.Brand.primary)
                .background(ColorsToken.Brand.primary.opacity(0.1))
                .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.medium))
            }
            .buttonStyle(PlainButtonStyle())
            
            // Start Workout (Primary)
            Button {
                let action = CardAction(kind: "accept_plan", label: "Accept", style: .primary, payload: serializePlan())
                handleAction(action, model)
            } label: {
                HStack(spacing: 6) {
                    Image(systemName: "checkmark")
                        .font(.system(size: 13, weight: .semibold))
                    Text("Start Workout")
                        .font(.system(size: 14, weight: .semibold))
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 12)
                .background(ColorsToken.Brand.primary)
                .foregroundColor(.white)
                .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.medium))
            }
            .buttonStyle(PlainButtonStyle())
        }
    }
    
    // MARK: - Plan Actions Sheet (rare/destructive only)
    
    @ViewBuilder
    private var planActionsSheet: some View {
        Button("Dismiss Plan", role: .destructive) {
            let action = CardAction(kind: "dismiss", label: "Dismiss", style: .destructive)
            handleAction(action, model)
        }
        Button("Report Issue", role: .none) {
            // TODO: Implement feedback
        }
        Button("Cancel", role: .cancel) {}
    }
    
    // MARK: - Edit Sheet (bottom sheet for prescription editing)
    
    private func editSheet(exercise: PlanExercise, index: Int) -> some View {
        let muscleText = exercise.primaryMuscles?.first ?? "this muscle group"
        let equipmentText = exercise.equipment ?? "similar equipment"
        
        return NavigationView {
            ScrollView {
                VStack(alignment: .leading, spacing: Space.lg) {
                    // Exercise header
                    VStack(alignment: .leading, spacing: Space.xs) {
                        Text(exercise.name)
                            .font(.system(size: 20, weight: .semibold))
                            .foregroundColor(ColorsToken.Text.primary)
                        
                        // Muscles & Equipment info
                        HStack(spacing: Space.md) {
                            if let muscles = exercise.primaryMuscles, !muscles.isEmpty {
                                HStack(spacing: 4) {
                                    Image(systemName: "figure.strengthtraining.traditional")
                                        .font(.system(size: 11))
                                    Text(muscles.joined(separator: ", "))
                                        .font(.system(size: 12))
                                }
                                .foregroundColor(ColorsToken.Text.secondary)
                            }
                            if let equip = exercise.equipment {
                                HStack(spacing: 4) {
                                    Image(systemName: "dumbbell")
                                        .font(.system(size: 11))
                                    Text(equip)
                                        .font(.system(size: 12))
                                }
                                .foregroundColor(ColorsToken.Text.secondary)
                            }
                        }
                    }
                    
                    Divider()
                    
                    // Set summary
                    VStack(alignment: .leading, spacing: Space.sm) {
                        Text("Prescription")
                            .font(.system(size: 13, weight: .semibold))
                            .foregroundColor(ColorsToken.Text.secondary)
                        
                        // Summary line using new computed property
                        Text(exercise.summaryLine)
                            .font(.system(size: 15, weight: .medium))
                            .foregroundColor(ColorsToken.Text.primary)
                        
                        // Show individual sets
                        ForEach(Array(exercise.sets.enumerated()), id: \.offset) { setIdx, planSet in
                            SetRowView(
                                setIndex: setIdx,
                                planSet: planSet,
                                isWarmup: planSet.isWarmup,
                                onEdit: { /* TODO: open set edit sheet */ }
                            )
                        }
                        
                        // Add set button
                        Button {
                            // Add a new working set with same prescription as last set
                            if let lastSet = editableExercises[safe: index]?.sets.last {
                                let newSet = PlanSet(type: .working, reps: lastSet.reps, weight: lastSet.weight, rir: lastSet.rir)
                                editableExercises[safe: index]?.sets.append(newSet)
                            } else {
                                let newSet = PlanSet(type: .working, reps: 8, weight: nil, rir: 2)
                                editableExercises[safe: index]?.sets.append(newSet)
                            }
                        } label: {
                            HStack {
                                Image(systemName: "plus.circle")
                                Text("Add Set")
                            }
                            .font(.system(size: 14, weight: .medium))
                            .foregroundColor(ColorsToken.Brand.primary)
                            .padding(.vertical, 8)
                        }
                        .buttonStyle(PlainButtonStyle())
                    }
                    
                    Divider()
                    
                    // Swap Options Section
                    VStack(alignment: .leading, spacing: Space.sm) {
                        Text("Swap Exercise")
                            .font(.system(size: 13, weight: .semibold))
                            .foregroundColor(ColorsToken.Text.secondary)
                        
                        VStack(spacing: Space.xs) {
                            swapOptionButton("Same Muscles", icon: "figure.strengthtraining.traditional", description: "Another \(muscleText) exercise") {
                                fireSwap(exercise: exercise, reason: "same_muscles")
                                exerciseForEdit = nil
                            }
                            
                            swapOptionButton("Same Equipment", icon: "dumbbell", description: "Another \(equipmentText) exercise") {
                                fireSwap(exercise: exercise, reason: "same_equipment")
                                exerciseForEdit = nil
                            }
                            
                            swapOptionButton("Different Variation", icon: "arrow.triangle.branch", description: "Target \(muscleText) from a different angle") {
                                fireSwap(exercise: exercise, reason: "different_angle")
                                exerciseForEdit = nil
                            }
                            
                            swapOptionButton("AI Suggestion", icon: "sparkles", description: "Let the coach pick the best alternative") {
                                fireSwap(exercise: exercise, reason: "ai_suggestion")
                                exerciseForEdit = nil
                            }
                        }
                    }
                    
                    Divider()
                    
                    // Bottom Actions
                    HStack(spacing: Space.md) {
                        Button {
                            exerciseForDetail = exercise
                            exerciseForEdit = nil
                        } label: {
                            HStack {
                                Image(systemName: "info.circle")
                                Text("Details")
                            }
                            .font(.system(size: 14, weight: .medium))
                            .foregroundColor(ColorsToken.Text.primary)
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 12)
                            .background(ColorsToken.Background.secondary)
                            .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.medium))
                        }
                        
                        Button {
                            removeExercise(at: index)
                            exerciseForEdit = nil
                        } label: {
                            HStack {
                                Image(systemName: "trash")
                                Text("Remove")
                            }
                            .font(.system(size: 14, weight: .medium))
                            .foregroundColor(.red)
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 12)
                            .background(Color.red.opacity(0.1))
                            .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.medium))
                        }
                    }
                    .buttonStyle(PlainButtonStyle())
                }
                .padding(Space.lg)
            }
            .background(ColorsToken.Surface.card)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Done") { exerciseForEdit = nil }
                        .font(.system(size: 15, weight: .semibold))
                }
            }
        }
        .presentationDetents([.large])
        .presentationDragIndicator(.visible)
    }
    
    private func stepperRow(_ label: String, value: Binding<Int>, range: ClosedRange<Int>, subtitle: String? = nil) -> some View {
        TappableStepperRow(
            label: label,
            subtitle: subtitle,
            value: Binding(
                get: { Double(value.wrappedValue) },
                set: { value.wrappedValue = Int($0.clamped(to: Double(range.lowerBound)...Double(range.upperBound))) }
            ),
            range: Double(range.lowerBound)...Double(range.upperBound),
            step: 1,
            formatValue: { String(format: "%.0f", $0) }
        )
    }
    
    private func weightStepperRow(_ label: String, value: Binding<Double?>, unit: String) -> some View {
        TappableWeightStepperRow(label: label, value: value, unit: unit)
    }
    
    private func swapOptionButton(_ title: String, icon: String, description: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: Space.sm) {
                Image(systemName: icon)
                    .font(.system(size: 16))
                    .foregroundColor(ColorsToken.Brand.primary)
                    .frame(width: 28)
                
                VStack(alignment: .leading, spacing: 2) {
                    Text(title)
                        .font(.system(size: 14, weight: .medium))
                        .foregroundColor(ColorsToken.Text.primary)
                    Text(description)
                        .font(.system(size: 12))
                        .foregroundColor(ColorsToken.Text.secondary)
                        .lineLimit(1)
                }
                
                Spacer()
                
                Image(systemName: "chevron.right")
                    .font(.system(size: 12))
                    .foregroundColor(ColorsToken.Text.secondary.opacity(0.5))
            }
            .padding(.horizontal, Space.sm)
            .padding(.vertical, 10)
            .background(ColorsToken.Background.secondary)
            .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.small))
        }
        .buttonStyle(PlainButtonStyle())
    }
    
    // MARK: - Actions
    
    private func fireAdjustment(_ instruction: String) {
        let action = CardAction(kind: "adjust_plan", label: instruction, payload: ["instruction": instruction, "current_plan": serializePlanForAgent()])
        handleAction(action, model)
    }
    
    private func fireSwap(exercise: PlanExercise, reason: String) {
        // Build muscle description with fallback to exercise name analysis
        let muscleDescription: String
        if let muscles = exercise.primaryMuscles, !muscles.isEmpty {
            muscleDescription = muscles.joined(separator: ", ")
        } else {
            // Derive from exercise name (common patterns)
            let nameLower = exercise.name.lowercased()
            if nameLower.contains("squat") || nameLower.contains("leg press") || nameLower.contains("lunge") {
                muscleDescription = "quadriceps, glutes"
            } else if nameLower.contains("deadlift") || nameLower.contains("hip thrust") {
                muscleDescription = "hamstrings, glutes"
            } else if nameLower.contains("bench") || nameLower.contains("chest") || nameLower.contains("fly") {
                muscleDescription = "chest"
            } else if nameLower.contains("row") || nameLower.contains("pull") || nameLower.contains("lat") {
                muscleDescription = "back, lats"
            } else if nameLower.contains("press") || nameLower.contains("shoulder") || nameLower.contains("delt") {
                muscleDescription = "shoulders"
            } else if nameLower.contains("curl") {
                muscleDescription = "biceps"
            } else if nameLower.contains("extension") || nameLower.contains("tricep") || nameLower.contains("pushdown") {
                muscleDescription = "triceps"
            } else {
                muscleDescription = "the same muscles"
            }
        }
        
        // Build equipment description with fallback
        let equipmentDescription: String
        if let equip = exercise.equipment, !equip.isEmpty {
            equipmentDescription = equip
        } else {
            // Derive from exercise name
            let nameLower = exercise.name.lowercased()
            if nameLower.contains("barbell") || nameLower.contains("bb ") {
                equipmentDescription = "barbell"
            } else if nameLower.contains("dumbbell") || nameLower.contains("db ") {
                equipmentDescription = "dumbbell"
            } else if nameLower.contains("cable") {
                equipmentDescription = "cable"
            } else if nameLower.contains("machine") {
                equipmentDescription = "machine"
            } else {
                equipmentDescription = "similar equipment"
            }
        }
        
        // Detailed instruction for agent (hidden from user)
        let instruction: String
        // User-visible AI response (shown immediately in chat)
        let visibleResponse: String
        
        switch reason {
        case "same_muscles":
            instruction = "Swap \(exercise.name) for another exercise targeting \(muscleDescription) but with different equipment. Keep the same sets/reps prescription."
            visibleResponse = "Let me find another \(muscleDescription) exercise with different equipment..."
        case "same_equipment":
            instruction = "Swap \(exercise.name) for another \(equipmentDescription) exercise targeting a different angle or variation. Keep the same sets/reps prescription."
            visibleResponse = "Let me find another \(equipmentDescription) exercise with a different angle..."
        case "different_angle":
            instruction = "Swap \(exercise.name) for a different variation that targets \(muscleDescription) from a different angle or movement pattern."
            visibleResponse = "Let me find a different movement pattern for \(muscleDescription)..."
        case "ai_suggestion":
            instruction = "Suggest the best replacement for \(exercise.name) that fits this workout's overall balance and the user's needs. Consider variety, muscle coverage, and available equipment."
            visibleResponse = "Let me pick the best alternative for \(exercise.name)..."
        default:
            instruction = "Swap \(exercise.name) for a suitable alternative."
            visibleResponse = "Let me find an alternative..."
        }
        
        let action = CardAction(kind: "swap_exercise", label: "Swap", payload: [
            "instruction": instruction,
            "exercise_id": exercise.exerciseId ?? "",
            "exercise_name": exercise.name,
            "swap_reason": reason,
            "target_muscles": muscleDescription,
            "target_equipment": equipmentDescription,
            "current_plan": serializePlanForAgent(),
            "hidden": "true",  // Don't show verbose instruction to user
            "ai_response": visibleResponse  // Show this immediately in chat
        ])
        handleAction(action, model)
    }
    
    private func serializePlan() -> [String: String] {
        guard let data = try? JSONEncoder().encode(editableExercises), let json = String(data: data, encoding: .utf8) else { return [:] }
        return ["exercises_json": json]
    }
    
    private func serializePlanForAgent() -> String {
        editableExercises.enumerated().map { i, ex in
            // Use summary line for agent readability
            return "\(i + 1). \(ex.name) — \(ex.summaryLine)"
        }.joined(separator: "\n")
    }
}

// MARK: - Set Row View

private struct SetRowView: View {
    let setIndex: Int
    let planSet: PlanSet
    let isWarmup: Bool
    let onEdit: () -> Void
    
    var body: some View {
        Button(action: onEdit) {
            HStack(spacing: Space.sm) {
                // Set label
                Text(setLabel)
                    .font(.system(size: 13, weight: .medium))
                    .foregroundColor(isWarmup ? ColorsToken.Text.secondary : ColorsToken.Text.primary)
                    .frame(width: 32, alignment: .leading)
                
                // Weight
                if let weight = planSet.weight, weight > 0 {
                    Text("\(Int(weight))kg")
                        .font(.system(size: 13))
                        .foregroundColor(ColorsToken.Text.primary)
                        .frame(width: 48, alignment: .leading)
                } else {
                    Text("—")
                        .font(.system(size: 13))
                        .foregroundColor(ColorsToken.Text.secondary.opacity(0.5))
                        .frame(width: 48, alignment: .leading)
                }
                
                // Reps
                Text("× \(planSet.reps)")
                    .font(.system(size: 13))
                    .foregroundColor(ColorsToken.Text.primary)
                    .frame(width: 36, alignment: .leading)
                
                // RIR (only for working sets)
                if !isWarmup, let rir = planSet.rir {
                    Text("RIR \(rir)")
                        .font(.system(size: 12))
                        .foregroundColor(ColorsToken.Text.secondary)
                }
                
                Spacer()
                
                // Chevron
                Image(systemName: "chevron.right")
                    .font(.system(size: 10))
                    .foregroundColor(ColorsToken.Text.secondary.opacity(0.4))
            }
            .padding(.vertical, 8)
            .padding(.horizontal, Space.sm)
            .background(isWarmup ? ColorsToken.Background.secondary.opacity(0.5) : ColorsToken.Background.secondary)
            .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.small))
        }
        .buttonStyle(PlainButtonStyle())
    }
    
    private var setLabel: String {
        if isWarmup {
            let warmupIndex = setIndex + 1 // 1-indexed for warm-ups
            return "WU\(warmupIndex)"
        } else {
            // Working set number (not counting warm-ups in this view)
            return "\(setIndex + 1)"
        }
    }
}

// MARK: - Swipeable Exercise Row

private struct SwipeableExerciseRow: View {
    let exercise: PlanExercise
    let onTap: () -> Void
    let onSwapLeft: () -> Void  // Remove
    let onSwapRight: () -> Void // Swap
    let onInfo: () -> Void
    
    @State private var offset: CGFloat = 0
    @GestureState private var dragOffset: CGFloat = 0
    
    private let swipeThreshold: CGFloat = 80
    
    var body: some View {
        ZStack {
            // Background actions (revealed on swipe)
            HStack(spacing: 0) {
                // Left action (swap) - revealed when swiping right
                Color.blue.opacity(0.9)
                    .overlay(
                        HStack {
                            Image(systemName: "arrow.left.arrow.right")
                                .font(.system(size: 18, weight: .medium))
                            Text("Swap")
                                .font(.system(size: 14, weight: .medium))
                        }
                        .foregroundColor(.white)
                        .padding(.leading, Space.md)
                        , alignment: .leading
                    )
                
                Spacer()
                
                // Right action (remove) - revealed when swiping left
                Color.red.opacity(0.9)
                    .overlay(
                        HStack {
                            Text("Remove")
                                .font(.system(size: 14, weight: .medium))
                            Image(systemName: "trash")
                                .font(.system(size: 18, weight: .medium))
                        }
                        .foregroundColor(.white)
                        .padding(.trailing, Space.md)
                        , alignment: .trailing
                    )
            }
            
            // Main content
            HStack(spacing: Space.sm) {
                // Exercise name and prescription
                VStack(alignment: .leading, spacing: 2) {
                    Text(exercise.name)
                        .font(.system(size: 15, weight: .medium))
                        .foregroundColor(ColorsToken.Text.primary)
                    
                    // Inline prescription: "4 × 8 @ RIR 2"
                    Text(prescriptionText)
                        .font(.system(size: 13))
                        .foregroundColor(ColorsToken.Text.secondary)
                }
                
                Spacer()
                
                // Chevron for tap to expand
                Image(systemName: "chevron.right")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(ColorsToken.Text.secondary.opacity(0.5))
            }
            .padding(.vertical, 12)
            .padding(.horizontal, Space.sm)
            .background(ColorsToken.Surface.card)
            .offset(x: offset + dragOffset)
            .gesture(
                DragGesture()
                    .updating($dragOffset) { value, state, _ in
                        state = value.translation.width
                    }
                    .onEnded { value in
                        let translation = value.translation.width
                        if translation > swipeThreshold {
                            // Swiped right -> Swap
                            withAnimation { offset = 0 }
                            onSwapRight()
                        } else if translation < -swipeThreshold {
                            // Swiped left -> Remove
                            withAnimation { offset = 0 }
                            onSwapLeft()
                        } else {
                            withAnimation { offset = 0 }
                        }
                    }
            )
            .onTapGesture { onTap() }
        }
        .frame(height: 56)
        .clipped()
    }
    
    private var prescriptionText: String {
        // Use the summary line from PlanExercise
        return exercise.summaryLine
    }
}

// MARK: - Tappable Stepper Row (supports both +/- buttons and direct input)

private struct TappableStepperRow: View {
    let label: String
    let subtitle: String?
    @Binding var value: Double
    let range: ClosedRange<Double>
    let step: Double
    let formatValue: (Double) -> String
    
    @State private var isEditing = false
    @State private var textValue = ""
    @FocusState private var isFocused: Bool
    
    init(label: String, subtitle: String? = nil, value: Binding<Double>, range: ClosedRange<Double>, step: Double = 1, formatValue: @escaping (Double) -> String) {
        self.label = label
        self.subtitle = subtitle
        self._value = value
        self.range = range
        self.step = step
        self.formatValue = formatValue
    }
    
    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(label)
                    .font(.system(size: 15, weight: .medium))
                    .foregroundColor(ColorsToken.Text.primary)
                if let sub = subtitle {
                    Text(sub)
                        .font(.system(size: 12))
                        .foregroundColor(ColorsToken.Text.secondary)
                }
            }
            
            Spacer()
            
            HStack(spacing: Space.sm) {
                // Minus button
                Button {
                    let newValue = max(range.lowerBound, value - step)
                    value = newValue
                } label: {
                    Image(systemName: "minus")
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundColor(value <= range.lowerBound ? ColorsToken.Text.secondary.opacity(0.3) : ColorsToken.Brand.primary)
                        .frame(width: 40, height: 40)
                        .background(ColorsToken.Background.secondary)
                        .clipShape(Circle())
                }
                .disabled(value <= range.lowerBound)
                
                // Tappable value (switches to TextField on tap) - fixed width to prevent jumping
                ZStack {
                    if isEditing {
                        TextField("", text: $textValue)
                            .keyboardType(.numberPad)
                            .multilineTextAlignment(.center)
                            .font(.system(size: 18, weight: .semibold))
                            .foregroundColor(ColorsToken.Text.primary)
                            .focused($isFocused)
                            .onSubmit { commitEdit() }
                            .onChange(of: isFocused) { focused in
                                if !focused { commitEdit() }
                            }
                    } else {
                        Button {
                            textValue = formatValue(value)
                            isEditing = true
                            DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
                                isFocused = true
                            }
                        } label: {
                            Text(formatValue(value))
                                .font(.system(size: 18, weight: .semibold))
                                .foregroundColor(ColorsToken.Text.primary)
                        }
                        .buttonStyle(PlainButtonStyle())
                    }
                }
                .frame(width: 52, height: 40)
                .background(isEditing ? ColorsToken.Background.secondary : ColorsToken.Background.secondary.opacity(0.5))
                .clipShape(RoundedRectangle(cornerRadius: 8))
                
                // Plus button
                Button {
                    let newValue = min(range.upperBound, value + step)
                    value = newValue
                } label: {
                    Image(systemName: "plus")
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundColor(value >= range.upperBound ? ColorsToken.Text.secondary.opacity(0.3) : ColorsToken.Brand.primary)
                        .frame(width: 40, height: 40)
                        .background(ColorsToken.Background.secondary)
                        .clipShape(Circle())
                }
                .disabled(value >= range.upperBound)
            }
            .buttonStyle(PlainButtonStyle())
        }
        .padding(.vertical, Space.xs)
    }
    
    private func commitEdit() {
        isEditing = false
        if let parsed = Double(textValue.replacingOccurrences(of: ",", with: ".")) {
            value = parsed.clamped(to: range)
        }
    }
}

// MARK: - Tappable Weight Stepper Row

private struct TappableWeightStepperRow: View {
    let label: String
    @Binding var value: Double?
    let unit: String
    
    @State private var isEditing = false
    @State private var textValue = ""
    @FocusState private var isFocused: Bool
    
    private var currentValue: Double { value ?? 0 }
    
    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(label)
                    .font(.system(size: 15, weight: .medium))
                    .foregroundColor(ColorsToken.Text.primary)
                Text("Target weight (\(unit))")
                    .font(.system(size: 12))
                    .foregroundColor(ColorsToken.Text.secondary)
            }
            
            Spacer()
            
            HStack(spacing: Space.sm) {
                // Minus button
                Button {
                    let newValue = max(0, currentValue - 2.5)
                    value = newValue > 0 ? newValue : nil
                } label: {
                    Image(systemName: "minus")
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundColor(currentValue <= 0 ? ColorsToken.Text.secondary.opacity(0.3) : ColorsToken.Brand.primary)
                        .frame(width: 40, height: 40)
                        .background(ColorsToken.Background.secondary)
                        .clipShape(Circle())
                }
                .disabled(currentValue <= 0)
                
                // Tappable value - fixed width to prevent jumping
                ZStack {
                    if isEditing {
                        HStack(spacing: 2) {
                            TextField("", text: $textValue)
                                .keyboardType(.decimalPad)
                                .multilineTextAlignment(.center)
                                .font(.system(size: 18, weight: .semibold))
                                .foregroundColor(ColorsToken.Text.primary)
                                .focused($isFocused)
                                .onSubmit { commitEdit() }
                                .onChange(of: isFocused) { focused in
                                    if !focused { commitEdit() }
                                }
                            Text(unit)
                                .font(.system(size: 11))
                                .foregroundColor(ColorsToken.Text.secondary)
                        }
                    } else {
                        Button {
                            textValue = currentValue > 0 ? formatWeight(currentValue) : ""
                            isEditing = true
                            DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
                                isFocused = true
                            }
                        } label: {
                            HStack(spacing: 2) {
                                if currentValue > 0 {
                                    Text(formatWeight(currentValue))
                                        .font(.system(size: 18, weight: .semibold))
                                        .foregroundColor(ColorsToken.Text.primary)
                                    Text(unit)
                                        .font(.system(size: 11))
                                        .foregroundColor(ColorsToken.Text.secondary)
                                } else {
                                    Text("—")
                                        .font(.system(size: 18, weight: .semibold))
                                        .foregroundColor(ColorsToken.Text.secondary.opacity(0.5))
                                }
                            }
                        }
                        .buttonStyle(PlainButtonStyle())
                    }
                }
                .frame(width: 70, height: 40)
                .background(isEditing ? ColorsToken.Background.secondary : ColorsToken.Background.secondary.opacity(0.5))
                .clipShape(RoundedRectangle(cornerRadius: 8))
                
                // Plus button
                Button {
                    value = currentValue + 2.5
                } label: {
                    Image(systemName: "plus")
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundColor(ColorsToken.Brand.primary)
                        .frame(width: 40, height: 40)
                        .background(ColorsToken.Background.secondary)
                        .clipShape(Circle())
                }
            }
            .buttonStyle(PlainButtonStyle())
        }
        .padding(.vertical, Space.xs)
    }
    
    private func formatWeight(_ w: Double) -> String {
        w.truncatingRemainder(dividingBy: 1) == 0
            ? String(format: "%.0f", w)
            : String(format: "%.1f", w)
    }
    
    private func commitEdit() {
        isEditing = false
        if let parsed = Double(textValue.replacingOccurrences(of: ",", with: ".")) {
            value = parsed > 0 ? parsed : nil
        } else if textValue.isEmpty {
            value = nil
        }
    }
}

// MARK: - Safe Array Access

private extension Array {
    subscript(safe index: Int) -> Element? {
        get { indices.contains(index) ? self[index] : nil }
        set {
            if let newValue = newValue, indices.contains(index) {
                self[index] = newValue
            }
        }
    }
}

// MARK: - Comparable Clamped Extension

private extension Comparable {
    func clamped(to range: ClosedRange<Self>) -> Self {
        min(max(self, range.lowerBound), range.upperBound)
    }
}

// MARK: - Inline Set Row (compact for expanded view)

private struct InlineSetRow: View {
    let setIndex: Int
    let planSet: PlanSet
    let onTap: () -> Void
    
    private var isWarmup: Bool { planSet.isWarmup }
    
    var body: some View {
        Button(action: onTap) {
            HStack(spacing: Space.sm) {
                // Set number/label
                Text(setLabel)
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundColor(isWarmup ? ColorsToken.Text.secondary : ColorsToken.Text.primary)
                    .frame(width: 28, alignment: .leading)
                
                // Weight
                if let weight = planSet.weight, weight > 0 {
                    Text("\(Int(weight))kg")
                        .font(.system(size: 13, weight: .medium))
                        .foregroundColor(ColorsToken.Text.primary)
                        .frame(width: 50, alignment: .leading)
                } else {
                    Text("—")
                        .font(.system(size: 13))
                        .foregroundColor(ColorsToken.Text.secondary.opacity(0.4))
                        .frame(width: 50, alignment: .leading)
                }
                
                // Reps
                Text("× \(planSet.reps)")
                    .font(.system(size: 13))
                    .foregroundColor(ColorsToken.Text.primary)
                    .frame(width: 34, alignment: .leading)
                
                // RIR badge (only for working sets)
                if !isWarmup {
                    if let rir = planSet.rir {
                        Text("RIR \(rir)")
                            .font(.system(size: 11, weight: .medium))
                            .foregroundColor(rirColor(rir))
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(rirColor(rir).opacity(0.12))
                            .clipShape(RoundedRectangle(cornerRadius: 4))
                    }
                }
                
                Spacer()
            }
            .padding(.vertical, 6)
            .padding(.horizontal, Space.xs)
            .background(isWarmup ? ColorsToken.Background.secondary.opacity(0.4) : ColorsToken.Surface.card)
            .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.small))
        }
        .buttonStyle(PlainButtonStyle())
    }
    
    private var setLabel: String {
        if isWarmup {
            return "WU"
        } else {
            return "\(setIndex + 1)"
        }
    }
    
    private func rirColor(_ rir: Int) -> Color {
        switch rir {
        case 0: return ColorsToken.State.error       // Failure
        case 1: return ColorsToken.State.warning     // Very hard
        case 2: return ColorsToken.Brand.primary     // Target
        case 3...5: return ColorsToken.Text.secondary // Easy/warmup-ish
        default: return ColorsToken.Text.secondary
        }
    }
}

// MARK: - Set Edit Sheet

private struct SetEditSheet: View {
    let exerciseName: String
    let setIndex: Int
    let set: PlanSet
    let isWarmup: Bool
    let onSave: (PlanSet) -> Void
    let onDelete: () -> Void
    let onDismiss: () -> Void
    
    @State private var editWeight: Double
    @State private var editReps: Int
    @State private var editRir: Int
    @State private var editIsWarmup: Bool
    
    init(exerciseName: String, setIndex: Int, set: PlanSet, isWarmup: Bool,
         onSave: @escaping (PlanSet) -> Void, onDelete: @escaping () -> Void, onDismiss: @escaping () -> Void) {
        self.exerciseName = exerciseName
        self.setIndex = setIndex
        self.set = set
        self.isWarmup = isWarmup
        self.onSave = onSave
        self.onDelete = onDelete
        self.onDismiss = onDismiss
        
        _editWeight = State(initialValue: set.weight ?? 0)
        _editReps = State(initialValue: set.reps)
        _editRir = State(initialValue: set.rir ?? 2)
        _editIsWarmup = State(initialValue: isWarmup)
    }
    
    private var setLabel: String {
        editIsWarmup ? "Warm-up Set" : "Set \(setIndex + 1)"
    }
    
    var body: some View {
        NavigationView {
            VStack(spacing: 0) {
                ScrollView {
                    VStack(alignment: .leading, spacing: Space.lg) {
                        // Header
                        VStack(alignment: .leading, spacing: Space.xs) {
                            Text(setLabel)
                                .font(.system(size: 24, weight: .bold))
                                .foregroundColor(ColorsToken.Text.primary)
                            Text(exerciseName)
                                .font(.system(size: 15))
                                .foregroundColor(ColorsToken.Text.secondary)
                        }
                        .padding(.bottom, Space.sm)
                        
                        // Weight input
                        VStack(alignment: .leading, spacing: Space.sm) {
                            Text("Weight")
                                .font(.system(size: 13, weight: .semibold))
                                .foregroundColor(ColorsToken.Text.secondary)
                            
                            HStack(spacing: Space.md) {
                                Button {
                                    editWeight = max(0, editWeight - 2.5)
                                } label: {
                                    Image(systemName: "minus")
                                        .font(.system(size: 18, weight: .semibold))
                                        .foregroundColor(editWeight <= 0 ? ColorsToken.Text.secondary.opacity(0.3) : ColorsToken.Brand.primary)
                                        .frame(width: 48, height: 48)
                                        .background(ColorsToken.Background.secondary)
                                        .clipShape(Circle())
                                }
                                .disabled(editWeight <= 0)
                                
                                VStack {
                                    Text(editWeight > 0 ? "\(Int(editWeight))" : "—")
                                        .font(.system(size: 32, weight: .bold))
                                        .foregroundColor(ColorsToken.Text.primary)
                                    Text("kg")
                                        .font(.system(size: 14))
                                        .foregroundColor(ColorsToken.Text.secondary)
                                }
                                .frame(width: 100)
                                
                                Button {
                                    editWeight += 2.5
                                } label: {
                                    Image(systemName: "plus")
                                        .font(.system(size: 18, weight: .semibold))
                                        .foregroundColor(ColorsToken.Brand.primary)
                                        .frame(width: 48, height: 48)
                                        .background(ColorsToken.Background.secondary)
                                        .clipShape(Circle())
                                }
                            }
                            .frame(maxWidth: .infinity)
                            .buttonStyle(PlainButtonStyle())
                        }
                        
                        Divider()
                        
                        // Reps input
                        VStack(alignment: .leading, spacing: Space.sm) {
                            Text("Reps")
                                .font(.system(size: 13, weight: .semibold))
                                .foregroundColor(ColorsToken.Text.secondary)
                            
                            HStack(spacing: Space.md) {
                                Button {
                                    editReps = max(1, editReps - 1)
                                } label: {
                                    Image(systemName: "minus")
                                        .font(.system(size: 18, weight: .semibold))
                                        .foregroundColor(editReps <= 1 ? ColorsToken.Text.secondary.opacity(0.3) : ColorsToken.Brand.primary)
                                        .frame(width: 48, height: 48)
                                        .background(ColorsToken.Background.secondary)
                                        .clipShape(Circle())
                                }
                                .disabled(editReps <= 1)
                                
                                Text("\(editReps)")
                                    .font(.system(size: 32, weight: .bold))
                                    .foregroundColor(ColorsToken.Text.primary)
                                    .frame(width: 100)
                                
                                Button {
                                    editReps = min(30, editReps + 1)
                                } label: {
                                    Image(systemName: "plus")
                                        .font(.system(size: 18, weight: .semibold))
                                        .foregroundColor(editReps >= 30 ? ColorsToken.Text.secondary.opacity(0.3) : ColorsToken.Brand.primary)
                                        .frame(width: 48, height: 48)
                                        .background(ColorsToken.Background.secondary)
                                        .clipShape(Circle())
                                }
                                .disabled(editReps >= 30)
                            }
                            .frame(maxWidth: .infinity)
                            .buttonStyle(PlainButtonStyle())
                        }
                        
                        // RIR input (only for working sets)
                        if !editIsWarmup {
                            Divider()
                            
                            VStack(alignment: .leading, spacing: Space.sm) {
                                Text("RIR (Reps in Reserve)")
                                    .font(.system(size: 13, weight: .semibold))
                                    .foregroundColor(ColorsToken.Text.secondary)
                                
                                HStack(spacing: Space.sm) {
                                    ForEach(0...5, id: \.self) { rir in
                                        Button {
                                            editRir = rir
                                        } label: {
                                            Text("\(rir)")
                                                .font(.system(size: 16, weight: .semibold))
                                                .foregroundColor(editRir == rir ? .white : ColorsToken.Text.primary)
                                                .frame(width: 44, height: 44)
                                                .background(editRir == rir ? rirColor(rir) : ColorsToken.Background.secondary)
                                                .clipShape(Circle())
                                        }
                                        .buttonStyle(PlainButtonStyle())
                                    }
                                }
                                
                                Text(rirDescription(editRir))
                                    .font(.system(size: 12))
                                    .foregroundColor(ColorsToken.Text.secondary)
                            }
                        }
                        
                        Divider()
                        
                        // Set type toggle
                        Toggle(isOn: $editIsWarmup) {
                            VStack(alignment: .leading, spacing: 2) {
                                Text("Warm-up Set")
                                    .font(.system(size: 15, weight: .medium))
                                    .foregroundColor(ColorsToken.Text.primary)
                                Text("Warm-up sets don't count towards volume")
                                    .font(.system(size: 12))
                                    .foregroundColor(ColorsToken.Text.secondary)
                            }
                        }
                        .tint(ColorsToken.Brand.primary)
                        
                        Spacer(minLength: Space.xl)
                        
                        // Delete button
                        Button {
                            onDelete()
                        } label: {
                            HStack {
                                Image(systemName: "trash")
                                Text("Delete Set")
                            }
                            .font(.system(size: 14, weight: .medium))
                            .foregroundColor(.red)
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 12)
                            .background(Color.red.opacity(0.1))
                            .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.medium))
                        }
                        .buttonStyle(PlainButtonStyle())
                    }
                    .padding(Space.lg)
                }
                
                // Save button
                VStack(spacing: 0) {
                    Divider()
                    Button {
                        let updatedSet = PlanSet(
                            id: set.id,
                            type: editIsWarmup ? .warmup : .working,
                            reps: editReps,
                            weight: editWeight > 0 ? editWeight : nil,
                            rir: editIsWarmup ? nil : editRir
                        )
                        onSave(updatedSet)
                    } label: {
                        Text("Save Changes")
                            .font(.system(size: 16, weight: .semibold))
                            .foregroundColor(.white)
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 14)
                            .background(ColorsToken.Brand.primary)
                            .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.medium))
                    }
                    .buttonStyle(PlainButtonStyle())
                    .padding(Space.md)
                }
            }
            .background(ColorsToken.Surface.card)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Cancel") { onDismiss() }
                        .foregroundColor(ColorsToken.Text.secondary)
                }
            }
        }
        .presentationDetents([.medium, .large])
        .presentationDragIndicator(.visible)
    }
    
    private func rirColor(_ rir: Int) -> Color {
        switch rir {
        case 0: return ColorsToken.State.error
        case 1: return ColorsToken.State.warning
        case 2: return ColorsToken.Brand.primary
        case 3...5: return ColorsToken.Text.secondary
        default: return ColorsToken.Text.secondary
        }
    }
    
    private func rirDescription(_ rir: Int) -> String {
        switch rir {
        case 0: return "Failure – could not complete another rep"
        case 1: return "Very hard – one rep left in the tank"
        case 2: return "Hard – two reps left in the tank (recommended)"
        case 3: return "Moderate – three reps left"
        case 4: return "Easy – four reps left"
        case 5: return "Very easy – five or more reps left"
        default: return ""
        }
    }
}
