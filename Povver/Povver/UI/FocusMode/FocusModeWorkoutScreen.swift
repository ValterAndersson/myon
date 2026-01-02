/**
 * FocusModeWorkoutScreen.swift
 * 
 * Full-screen workout execution view - Premium Execution Surface.
 * 
 * Design principles:
 * - Strong depth + hierarchy with card elevation system
 * - Fast set entry with inline editing dock
 * - AI Copilot as first-class control (Coach button)
 * - Mode-driven reordering with visual mode distinction
 * - Finish action at bottom of flow, not header
 */

import SwiftUI

struct FocusModeWorkoutScreen: View {
    @StateObject private var service = FocusModeWorkoutService.shared
    @Environment(\.dismiss) private var dismiss
    
    // Workout source (template, routine, or empty)
    let sourceTemplateId: String?
    let sourceRoutineId: String?
    let workoutName: String?
    
    // MARK: - State Machine
    @State private var screenMode: FocusModeScreenMode = .normal
    @State private var activeSheet: FocusModeActiveSheet? = nil
    @State private var pendingSheetTask: Task<Void, Never>? = nil
    
    // List edit mode binding (synced with screenMode)
    @State private var listEditMode: EditMode = .inactive
    
    // Reorder toggle debounce
    @State private var isReorderTransitioning = false
    
    // Scroll tracking for hero collapse with hysteresis
    @State private var isHeroCollapsed = false
    @State private var measuredHeroHeight: CGFloat = 280  // Will be measured dynamically
    
    // Debug: Show scroll values (set to true for debugging)
    #if DEBUG
    @State private var debugScrollMinY: CGFloat = 0
    #endif
    
    // Timer state
    @State private var elapsedTime: TimeInterval = 0
    @State private var timer: Timer?
    
    // Editor state
    @State private var editingName: String = ""
    @State private var editingStartTime: Date = Date()
    
    // Confirmation dialogs
    @State private var showingCancelConfirmation = false
    @State private var showingCompleteConfirmation = false
    @State private var showingNameEditor = false
    
    // Prevents duplicate starts
    @State private var isStartingWorkout = false
    
    init(
        templateId: String? = nil,
        routineId: String? = nil,
        name: String? = nil
    ) {
        self.sourceTemplateId = templateId
        self.sourceRoutineId = routineId
        self.workoutName = name
    }
    
    // MARK: - Computed Properties
    
    /// Derive selectedCell from screenMode for backward compatibility
    private var selectedCell: Binding<FocusModeGridCell?> {
        Binding(
            get: {
                if case .editingSet(let exerciseId, let setId, let cellType) = screenMode {
                    switch cellType {
                    case .weight: return .weight(exerciseId: exerciseId, setId: setId)
                    case .reps: return .reps(exerciseId: exerciseId, setId: setId)
                    case .rir: return .rir(exerciseId: exerciseId, setId: setId)
                    }
                }
                return nil
            },
            set: { newValue in
                if let cell = newValue {
                    let cellType: FocusModeEditCellType
                    switch cell {
                    case .weight: cellType = .weight
                    case .reps: cellType = .reps
                    case .rir: cellType = .rir
                    case .done: cellType = .weight  // Default to weight for done cells
                    }
                    screenMode = .editingSet(exerciseId: cell.exerciseId, setId: cell.setId, cellType: cellType)
                } else {
                    screenMode = .normal
                }
            }
        )
    }
    
    /// Active exercise based on current mode or first incomplete
    private var activeExerciseId: String? {
        if case .editingSet(let exerciseId, _, _) = screenMode {
            return exerciseId
        }
        return service.workout?.exercises.first { !$0.isComplete }?.instanceId
    }
    
    /// Total and completed sets for progress display
    private var totalSets: Int {
        service.workout?.exercises.flatMap { $0.sets }.count ?? 0
    }
    
    private var completedSets: Int {
        service.workout?.exercises.flatMap { $0.sets }.filter { $0.isDone }.count ?? 0
    }
    
    var body: some View {
        GeometryReader { geometry in
            VStack(spacing: 0) {
                // Custom header bar (always visible)
                customHeaderBar
                
                // Reorder mode banner
                if screenMode.isReordering {
                    ReorderModeBanner(onDone: toggleReorderMode)
                }
                
                // Main content
                ZStack {
                    ColorsToken.Background.screen.ignoresSafeArea()
                    
                    if service.isLoading {
                        loadingView
                    } else if let workout = service.workout {
                        workoutContent(workout, safeAreaBottom: geometry.safeAreaInsets.bottom)
                    } else {
                        workoutStartView
                    }
                }
            }
            .background(ColorsToken.Background.screen)
        }
        .navigationBarHidden(true)
        .toolbar(.hidden, for: .tabBar)  // Hide tab bar in Focus Mode
        .interactiveDismissDisabled(service.workout != nil)
        .onChange(of: screenMode) { _, newMode in
            // Sync List editMode with screenMode
            listEditMode = newMode.isReordering ? .active : .inactive
        }
        .confirmationDialog("Finish Workout?", isPresented: $showingCompleteConfirmation) {
            Button("Complete Workout") {
                finishWorkout()
            }
            Button("Keep Logging", role: .cancel) { }
        }
        .alert("Workout Name", isPresented: $showingNameEditor) {
            TextField("Name", text: $editingName)
            Button("Save") {
                updateWorkoutName(editingName)
            }
            Button("Cancel", role: .cancel) { }
        }
        .alert("Discard Workout?", isPresented: $showingCancelConfirmation) {
            Button("Keep Logging", role: .cancel) { }
            Button("Discard", role: .destructive) {
                discardWorkout()
            }
        } message: {
            Text("Your progress will not be saved.")
        }
        .sheet(item: $activeSheet) { sheet in
            sheetContent(for: sheet)
        }
        .task {
            await startWorkoutIfNeeded()
        }
    }
    
    // MARK: - Sheet Content
    
    @ViewBuilder
    private func sheetContent(for sheet: FocusModeActiveSheet) -> some View {
        switch sheet {
        case .coach:
            aiPanelPlaceholder
        case .exerciseSearch:
            FocusModeExerciseSearch { exercise in
                addExercise(exercise)
                activeSheet = nil
            }
        case .startTimeEditor:
            startTimeEditorSheet
        case .finishWorkout:
            FinishWorkoutSheet(
                elapsedTime: elapsedTime,
                completedSets: completedSets,
                totalSets: totalSets,
                exerciseCount: service.workout?.exercises.count ?? 0,
                onComplete: {
                    activeSheet = nil
                    finishWorkout()
                },
                onDiscard: {
                    activeSheet = nil
                    showingCancelConfirmation = true
                },
                onDismiss: {
                    activeSheet = nil
                }
            )
        case .setTypePicker, .moreActions:
            // Handled in FocusModeSetGrid
            EmptyView()
        }
    }
    
    // MARK: - Sheet Presentation Helper
    
    /// Present a sheet with deterministic gating:
    /// - Clears editor/reorder mode first
    /// - Waits for animation to complete before presenting
    private func presentSheet(_ sheet: FocusModeActiveSheet) {
        // Cancel any pending presentation
        pendingSheetTask?.cancel()
        
        if screenMode.isReordering {
            // Exit reorder mode first
            withAnimation(.easeOut(duration: 0.2)) {
                screenMode = .normal
            }
            // Wait for animation to complete, then present on next run loop
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) {
                guard self.screenMode == .normal, self.activeSheet == nil else { return }
                self.activeSheet = sheet
            }
        } else if screenMode.isEditing {
            // Close editor first
            withAnimation(.easeOut(duration: 0.15)) {
                screenMode = .normal
            }
            // Wait for animation to complete, then present
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) {
                guard self.screenMode == .normal, self.activeSheet == nil else { return }
                self.activeSheet = sheet
            }
        } else {
            activeSheet = sheet
        }
    }
    
    // MARK: - Reorder Toggle
    
    private func toggleReorderMode() {
        guard !isReorderTransitioning else { return }
        
        isReorderTransitioning = true
        
        // Exit editing mode first if needed
        if screenMode.isEditing {
            withAnimation(.easeOut(duration: 0.15)) {
                screenMode = .normal
            }
        }
        
        withAnimation(.spring(response: 0.3)) {
            screenMode = screenMode.isReordering ? .normal : .reordering
        }
        
        UIImpactFeedbackGenerator(style: .medium).impactOccurred()
        
        // Re-enable after transition
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) {
            isReorderTransitioning = false
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
    private func workoutContent(_ workout: FocusModeWorkout, safeAreaBottom: CGFloat) -> some View {
        if screenMode.isReordering {
            // Reorder mode: simplified list with drag handles
            // All other interactions are disabled
            List {
                ForEach(workout.exercises) { exercise in
                    ExerciseReorderRow(exercise: exercise)
                        .listRowBackground(Color.clear)
                        .listRowSeparator(.hidden)
                        .listRowInsets(EdgeInsets(top: 6, leading: 16, bottom: 6, trailing: 16))
                }
                .onMove { from, to in
                    reorderExercisesNew(from: from, to: to)
                }
            }
            .listStyle(.plain)
            .scrollContentBackground(.hidden)
            .environment(\.editMode, $listEditMode)
        } else {
            // Normal mode: Hero + exercise sections with scroll tracking
            ScrollView {
                LazyVStack(spacing: 0, pinnedViews: []) {
                    // Constant 8pt top padding - always present, no jumpiness
                    Color.clear.frame(height: Space.sm)
                    
                    // HERO: Workout identity + large timer
                    // Use .onGeometryChange for continuous scroll tracking (iOS 16+)
                    WorkoutHero(
                        workoutName: workout.name ?? "Workout",
                        startTime: workout.startTime,
                        elapsedTime: elapsedTime,
                        completedSets: completedSets,
                        totalSets: totalSets,
                        hasExercises: !workout.exercises.isEmpty,
                        onNameTap: {
                            editingName = workout.name ?? "Workout"
                            showingNameEditor = true
                        },
                        onTimerTap: {
                            presentSheet(.startTimeEditor)
                        },
                        onCoachTap: {
                            presentSheet(.coach)
                        },
                        onReorderTap: toggleReorderMode,
                        onMenuAction: { action in
                            handleHeroMenuAction(action, workout: workout)
                        }
                    )
                    .onGeometryChange(for: CGRect.self) { proxy in
                        proxy.frame(in: .named("workoutScroll"))
                    } action: { newFrame in
                        // Continuous scroll tracking via onGeometryChange
                        let heroBottom = newFrame.maxY
                        let collapseThreshold: CGFloat = 100
                        let expandThreshold: CGFloat = 150
                        
                        #if DEBUG
                        debugScrollMinY = newFrame.minY
                        // Throttled debug logging
                        if Int(newFrame.minY) % 50 == 0 {
                            print("🔍 [ScrollDebug] heroMinY=\(Int(newFrame.minY)) heroMaxY=\(Int(heroBottom)) collapsed=\(isHeroCollapsed)")
                        }
                        #endif
                        
                        // Hysteresis-based collapse detection
                        if heroBottom < collapseThreshold && !isHeroCollapsed {
                            print("🔍 [ScrollDebug] → COLLAPSING")
                            withAnimation(.easeInOut(duration: 0.15)) {
                                isHeroCollapsed = true
                            }
                        } else if heroBottom > expandThreshold && isHeroCollapsed {
                            print("🔍 [ScrollDebug] → EXPANDING")
                            withAnimation(.easeInOut(duration: 0.15)) {
                                isHeroCollapsed = false
                            }
                        }
                        
                        // Update measured height
                        if newFrame.height > 0 {
                            measuredHeroHeight = newFrame.height
                        }
                    }
                    
                    // Empty state OR exercise list
                    if workout.exercises.isEmpty {
                        // Empty state: instructional card
                        EmptyStateCard {
                            presentSheet(.exerciseSearch)
                        }
                        .padding(.top, Space.lg)
                    } else {
                        // Exercises - each as a card with full set grid
                        ForEach(workout.exercises) { exercise in
                            let isActive = exercise.instanceId == activeExerciseId
                            
                            ExerciseCardContainer(isActive: isActive) {
                                FocusModeExerciseSectionNew(
                                    exercise: exercise,
                                    isActive: isActive,
                                    screenMode: $screenMode,
                                    onLogSet: logSet,
                                    onPatchField: patchField,
                                    onAddSet: { addSet(to: exercise.instanceId) },
                                    onRemoveSet: { setId in removeSet(exerciseId: exercise.instanceId, setId: setId) },
                                    onAutofill: { autofillExercise(exercise.instanceId) }
                                )
                            }
                            .padding(.top, Space.md)
                        }
                        
                        // Add Exercise Button (hidden during reorder mode via parent check)
                        addExerciseButton
                            .padding(.top, Space.lg)
                        
                        // Bottom CTA Section: Finish + Discard
                        bottomCTASection(safeAreaBottom: safeAreaBottom)
                    }
                }
                .padding(.horizontal, Space.md)
            }
            .coordinateSpace(name: "workoutScroll")
            .onPreferenceChange(ScrollOffsetPreferenceKey.self) { scrollY in
                // Scroll offset based collapse detection:
                // scrollY = 0 when at top, becomes negative when scrolling up
                // Hero is at offset 8 (spacer) with height ~280
                // Hero bottom = 8 + 280 = 288
                // When scrolled, hero bottom = 288 + scrollY
                
                let heroStartY: CGFloat = Space.sm  // 8pt spacer
                let heroHeight = measuredHeroHeight  // ~280pt
                let heroBottom = heroStartY + heroHeight + scrollY
                
                let collapseThreshold: CGFloat = 100  // Collapse when only 100pt of hero visible
                let expandThreshold: CGFloat = 150   // Expand when 150pt of hero visible
                
                #if DEBUG
                debugScrollMinY = scrollY
                // Debug log to understand scroll behavior (throttled - only log on significant change)
                if abs(scrollY.truncatingRemainder(dividingBy: 50)) < 5 {
                    print("🔍 [ScrollDebug] scrollY=\(Int(scrollY)) heroBottom=\(Int(heroBottom)) collapsed=\(isHeroCollapsed)")
                }
                #endif
                
                // Only update if crossing threshold in correct direction (hysteresis)
                if heroBottom < collapseThreshold && !isHeroCollapsed {
                    print("🔍 [ScrollDebug] → COLLAPSING (heroBottom \(Int(heroBottom)) < \(Int(collapseThreshold)))")
                    withAnimation(.easeInOut(duration: 0.15)) { 
                        isHeroCollapsed = true 
                    }
                } else if heroBottom > expandThreshold && isHeroCollapsed {
                    print("🔍 [ScrollDebug] → EXPANDING (heroBottom \(Int(heroBottom)) > \(Int(expandThreshold)))")
                    withAnimation(.easeInOut(duration: 0.15)) { 
                        isHeroCollapsed = false 
                    }
                }
            }
            .scrollDismissesKeyboard(.interactively)
        }
    }
    
    /// Handle hero menu actions
    private func handleHeroMenuAction(_ action: WorkoutHero.HeroMenuAction, workout: FocusModeWorkout) {
        switch action {
        case .editName:
            editingName = workout.name ?? "Workout"
            showingNameEditor = true
        case .editStartTime:
            presentSheet(.startTimeEditor)
        case .reorder:
            toggleReorderMode()
        case .discard:
            showingCancelConfirmation = true
        }
    }
    
    // MARK: - Reorder Exercises
    
    private func reorderExercisesNew(from source: IndexSet, to destination: Int) {
        // Apply the reorder to the service
        service.reorderExercises(from: source, to: destination)
        UIImpactFeedbackGenerator(style: .medium).impactOccurred()
    }
    
    // MARK: - Computed Flags for Nav
    
    /// Whether to show collapsed actions (Coach/Reorder/More)
    /// True when hero is collapsed AND not in reorder mode
    private var showCollapsedActions: Bool {
        isHeroCollapsed && !screenMode.isReordering
    }
    
    /// Whether reorder is possible (>= 2 exercises)
    private var canReorder: Bool {
        (service.workout?.exercises.count ?? 0) >= 2
    }
    
    // MARK: - Nav Bar (Simplified: Timer center, Reorder, AI)
    
    /// Simplified nav bar:
    /// - Timer always centered
    /// - Reorder + AI icons appear on right when collapsed
    /// - No ellipsis, no Finish button (moved to bottom)
    /// - No workout title
    private var customHeaderBar: some View {
        VStack(spacing: 0) {
            if service.workout != nil {
                ZStack {
                    // CENTER LAYER: Timer (truly centered)
                    NavCompactTimer(elapsedTime: elapsedTime) {
                        presentSheet(.startTimeEditor)
                    }
                    .opacity(isHeroCollapsed ? 1.0 : 0.65)
                    
                    // RIGHT ZONE ONLY: Reorder + AI icons (order: Reorder, AI)
                    HStack {
                        Spacer()
                        
                        HStack(spacing: 4) {
                            // Reorder icon - only when collapsed, has exercises, and not reordering
                            Button {
                                if canReorder { toggleReorderMode() }
                            } label: {
                                Image(systemName: "arrow.up.arrow.down")
                                    .font(.system(size: 16, weight: .medium))
                                    .foregroundColor(canReorder ? ColorsToken.Text.secondary : ColorsToken.Text.muted)
                                    .frame(width: 44, height: 44)
                                    .contentShape(Rectangle())
                            }
                            .buttonStyle(PlainButtonStyle())
                            .opacity(showCollapsedActions && canReorder ? 1.0 : 0)
                            .allowsHitTesting(showCollapsedActions && canReorder)
                            .accessibilityHidden(!(showCollapsedActions && canReorder))
                            .accessibilityLabel("Reorder exercises")
                            
                            // Coach/AI icon - only when collapsed and not reordering
                            Button {
                                presentSheet(.coach)
                            } label: {
                                Image(systemName: "sparkles")
                                    .font(.system(size: 18, weight: .medium))
                                    .foregroundColor(ColorsToken.Brand.primary)
                                    .frame(width: 44, height: 44)
                                    .contentShape(Rectangle())
                            }
                            .buttonStyle(PlainButtonStyle())
                            .opacity(showCollapsedActions ? 1.0 : 0)
                            .allowsHitTesting(showCollapsedActions)
                            .accessibilityHidden(!showCollapsedActions)
                            .accessibilityLabel("Coach")
                        }
                    }
                }
                .frame(height: 52)  // Fixed nav bar height
                .padding(.horizontal, Space.md)
                .animation(.easeInOut(duration: 0.2), value: isHeroCollapsed)
                .animation(.easeInOut(duration: 0.2), value: screenMode.isReordering)
            } else {
                // Pre-workout state
                HStack {
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
                            .frame(width: 44, height: 44)
                            .contentShape(Rectangle())
                    }
                    .buttonStyle(PlainButtonStyle())
                }
                .frame(height: 52)  // Fixed nav bar height
                .padding(.horizontal, Space.md)
            }
            
            Divider()
        }
        .background(ColorsToken.Background.screen)
    }
    
    // MARK: - Start Time Editor Sheet
    
    private var startTimeEditorSheet: some View {
        NavigationStack {
            VStack(spacing: 0) {
                // Time picker - wheel style with explicit height
                DatePicker(
                    "",
                    selection: $editingStartTime,
                    in: ...Date(),
                    displayedComponents: [.date, .hourAndMinute]
                )
                .datePickerStyle(.wheel)
                .labelsHidden()
                .frame(height: 216)  // Standard wheel picker height
                .frame(maxWidth: .infinity)
                .padding(.top, Space.lg)
                
                // Timezone info
                HStack {
                    Image(systemName: "globe")
                        .foregroundColor(ColorsToken.Text.secondary)
                    Text(TimeZone.current.identifier)
                        .font(.system(size: 14))
                        .foregroundColor(ColorsToken.Text.secondary)
                    Spacer()
                }
                .padding(.horizontal, Space.lg)
                .padding(.top, Space.md)
                
                Spacer()
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
            .background(Color(uiColor: .systemBackground))
            .navigationTitle("Edit Start Time")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") {
                        activeSheet = nil
                    }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        Task {
                            do {
                                try await service.updateStartTime(editingStartTime)
                                print("✅ Start time updated to: \(editingStartTime)")
                            } catch {
                                print("❌ Failed to update start time: \(error)")
                            }
                        }
                        activeSheet = nil
                    }
                }
            }
            .onAppear {
                editingStartTime = service.workout?.startTime ?? Date()
            }
        }
        .presentationDetents([.large])
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
            do {
                try await service.updateWorkoutName(name)
                print("✅ Workout name updated to: \(name)")
            } catch {
                print("❌ Failed to update workout name: \(error)")
            }
        }
    }
    
    private func discardWorkout() {
        stopTimer()
        Task {
            do {
                try await service.cancelWorkout()
                print("✅ Workout discarded")
                // Dismiss after successful cancel
                await MainActor.run {
                    dismiss()
                }
            } catch {
                print("❌ Failed to discard workout: \(error)")
                // Still dismiss even on error (local state is cleared)
                await MainActor.run {
                    dismiss()
                }
            }
        }
    }
    
    private func finishWorkout() {
        stopTimer()
        Task {
            do {
                let archivedId = try await service.completeWorkout()
                print("✅ Workout completed and archived with ID: \(archivedId)")
                // TODO: Show summary screen with archivedId
                await MainActor.run {
                    dismiss()
                }
            } catch {
                print("❌ Failed to complete workout: \(error)")
                // Still dismiss on error
                await MainActor.run {
                    dismiss()
                }
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
                    Button("Done") { activeSheet = nil }
                }
            }
        }
        .presentationDetents([.medium])
    }
    
    // MARK: - Add Exercise Button
    
    private var addExerciseButton: some View {
        Button { presentSheet(.exerciseSearch) } label: {
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
    
    // MARK: - Bottom CTA Section
    
    /// Bottom CTA section with Finish and Discard buttons
    /// This replaces the nav bar Finish button for better layout
    private func bottomCTASection(safeAreaBottom: CGFloat) -> some View {
        VStack(spacing: Space.md) {
            // Finish Workout - Primary CTA
            Button {
                presentSheet(.finishWorkout)
            } label: {
                Text("Finish Workout")
                    .font(.system(size: 17, weight: .semibold))
                    .foregroundColor(.white)
                    .frame(maxWidth: .infinity)
                    .frame(height: 52)
                    .background(ColorsToken.Brand.emeraldFill)
                    .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.medium))
            }
            .buttonStyle(PlainButtonStyle())
            
            // Discard Workout - Destructive secondary (text link style)
            Button {
                showingCancelConfirmation = true
            } label: {
                Text("Discard Workout")
                    .font(.system(size: 15, weight: .medium))
                    .foregroundColor(ColorsToken.State.error)
            }
            .buttonStyle(PlainButtonStyle())
        }
        .padding(.top, Space.xl)
        .padding(.bottom, safeAreaBottom + Space.lg)
    }
    
    // MARK: - Timer
    
    /// Start the elapsed time timer. Guards against double-start.
    /// Timer derives elapsed time from workout.startTime (single source of truth).
    private func startTimer() {
        guard let workout = service.workout else { return }
        
        // Guard against double-start
        guard timer == nil else { return }
        
        // Reset UI state
        screenMode = .normal
        elapsedTime = Date().timeIntervalSince(workout.startTime)
        
        timer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { _ in
            Task { @MainActor in
                if let workout = service.workout {
                    elapsedTime = Date().timeIntervalSince(workout.startTime)
                }
            }
        }
    }
    
    /// Stop the timer and reset elapsed time.
    private func stopTimer() {
        timer?.invalidate()
        timer = nil
        elapsedTime = 0
    }
    
    /// Reset timer state for a new workout (derives from new startTime).
    private func resetTimerForNewWorkout() {
        stopTimer()
        startTimer()
    }
    
    // MARK: - Actions
    
    private func startWorkoutIfNeeded() async {
        // Existing workout - just start timer
        guard service.workout == nil else {
            startTimer()
            return
        }
        
        // Guard against duplicate concurrent starts
        guard !isStartingWorkout else { return }
        
        if sourceTemplateId != nil || sourceRoutineId != nil {
            isStartingWorkout = true
            defer { isStartingWorkout = false }
            
            do {
                _ = try await service.startWorkout(
                    name: workoutName,
                    sourceTemplateId: sourceTemplateId,
                    sourceRoutineId: sourceRoutineId
                )
                resetTimerForNewWorkout()
            } catch {
                print("Failed to start workout: \(error)")
            }
        }
    }
    
    private func startEmptyWorkout() async {
        // Guard against duplicate concurrent starts
        guard !isStartingWorkout else { return }
        
        isStartingWorkout = true
        defer { isStartingWorkout = false }
        
        do {
            _ = try await service.startWorkout(name: "Workout")
            resetTimerForNewWorkout()
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

// MARK: - Exercise Section New (with ActionRail and screenMode binding)

struct FocusModeExerciseSectionNew: View {
    let exercise: FocusModeExercise
    let isActive: Bool
    @Binding var screenMode: FocusModeScreenMode
    
    let onLogSet: (String, String, Double?, Int, Int?) -> Void
    let onPatchField: (String, String, String, Any) -> Void
    let onAddSet: () -> Void
    let onRemoveSet: (String) -> Void
    let onAutofill: () -> Void
    
    /// Derive selectedCell from screenMode for this exercise
    private var selectedCell: Binding<FocusModeGridCell?> {
        Binding(
            get: {
                if case .editingSet(let exerciseId, let setId, let cellType) = screenMode,
                   exerciseId == exercise.instanceId {
                    switch cellType {
                    case .weight: return .weight(exerciseId: exerciseId, setId: setId)
                    case .reps: return .reps(exerciseId: exerciseId, setId: setId)
                    case .rir: return .rir(exerciseId: exerciseId, setId: setId)
                    }
                }
                return nil
            },
            set: { newValue in
                if let cell = newValue {
                    let cellType: FocusModeEditCellType
                    switch cell {
                    case .weight: cellType = .weight
                    case .reps: cellType = .reps
                    case .rir: cellType = .rir
                    case .done: cellType = .weight
                    }
                    screenMode = .editingSet(exerciseId: cell.exerciseId, setId: cell.setId, cellType: cellType)
                } else {
                    screenMode = .normal
                }
            }
        )
    }
    
    /// Build action items for the ActionRail
    private var actionItems: [ActionItem] {
        [
            ActionItem(
                icon: "sparkles",
                label: "Auto-fill",
                priority: .coach,
                isPrimary: true,
                action: onAutofill
            ),
            ActionItem(
                icon: "arrow.up",
                label: "+2.5kg",
                priority: .utility,
                isPrimary: false,
                action: { /* TODO: Suggest weight increase */ }
            ),
            ActionItem(
                icon: "clock.arrow.circlepath",
                label: "Last Time",
                priority: .utility,
                isPrimary: false,
                action: { /* TODO: Use last performance */ }
            )
        ]
    }
    
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Exercise Header
            exerciseHeader
            
            // Action Rail (structured AI actions)
            ActionRail(
                actions: actionItems,
                isActive: isActive,
                onMoreTap: { /* TODO: Show more actions sheet */ }
            )
            
            // Set Grid with warmup divider
            FocusModeSetGrid(
                exercise: exercise,
                selectedCell: selectedCell,
                onLogSet: onLogSet,
                onPatchField: onPatchField,
                onAddSet: onAddSet,
                onRemoveSet: onRemoveSet
            )
        }
    }
    
    private var exerciseHeader: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(exercise.name)
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundColor(ColorsToken.Text.primary)
                
                Text("\(exercise.completedSetsCount)/\(exercise.totalWorkingSetsCount) sets")
                    .font(.system(size: 13).monospacedDigit())
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
