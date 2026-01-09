import SwiftUI

/// Library Tab - Content assets and reference catalog
/// Simple list landing with Routines, Templates, Exercises sections
struct LibraryView: View {
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Space.lg) {
                // Header
                VStack(alignment: .leading, spacing: Space.xs) {
                    Text("Library")
                        .font(.system(size: 28, weight: .bold))
                        .foregroundColor(Color.textPrimary)
                    
                    Text("Your training assets and content")
                        .font(.system(size: 15))
                        .foregroundColor(Color.textSecondary)
                }
                .padding(.horizontal, Space.lg)
                .padding(.top, Space.md)
                
                // Library sections - monochrome icons for premium aesthetic
                VStack(spacing: Space.sm) {
                    // Routines
                    NavigationLink(destination: RoutinesListView()) {
                        LibraryRow(
                            title: "Routines",
                            subtitle: "Weekly training programs",
                            icon: "calendar"
                        )
                    }
                    .buttonStyle(PlainButtonStyle())
                    
                    // Templates
                    NavigationLink(destination: TemplatesListView()) {
                        LibraryRow(
                            title: "Templates",
                            subtitle: "Reusable workout templates",
                            icon: "doc.on.doc"
                        )
                    }
                    .buttonStyle(PlainButtonStyle())
                    
                    // Exercises
                    NavigationLink(destination: ExercisesListView()) {
                        LibraryRow(
                            title: "Exercises",
                            subtitle: "Exercise catalog and movements",
                            icon: "figure.strengthtraining.traditional"
                        )
                    }
                    .buttonStyle(PlainButtonStyle())
                }
                .padding(.horizontal, Space.lg)
                
                Spacer(minLength: Space.xxl)
            }
        }
        .background(Color.bg)
        .navigationTitle("")
        .navigationBarTitleDisplayMode(.inline)
    }
}

// MARK: - Library Row

private struct LibraryRow: View {
    let title: String
    let subtitle: String
    let icon: String
    
    var body: some View {
        HStack(spacing: Space.md) {
            // Icon - monochrome for premium aesthetic
            Image(systemName: icon)
                .font(.system(size: 20))
                .foregroundColor(Color.textSecondary)
                .frame(width: 44, height: 44)
                .background(Color.surfaceElevated)
                .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.small))
            
            // Text
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(Color.textPrimary)
                
                Text(subtitle)
                    .font(.system(size: 13))
                    .foregroundColor(Color.textSecondary)
            }
            
            Spacer()
            
            // Chevron
            Image(systemName: "chevron.right")
                .font(.system(size: 14, weight: .medium))
                .foregroundColor(Color.textTertiary)
        }
        .padding(Space.md)
        .background(Color.surface)
        .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.medium))
        .overlay(
            RoundedRectangle(cornerRadius: CornerRadiusToken.medium)
                .stroke(Color.separatorLine, lineWidth: StrokeWidthToken.hairline)
        )
    }
}

// MARK: - Routines List View (Scaffold)

struct RoutinesListView: View {
    @State private var routines: [RoutineItem] = []
    @State private var isLoading = true
    
    var body: some View {
        Group {
            if isLoading {
                loadingView
            } else if routines.isEmpty {
                emptyStateView
            } else {
                routinesList
            }
        }
        .background(Color.bg)
        .navigationTitle("Routines")
        .navigationBarTitleDisplayMode(.large)
        .task {
            await loadRoutines()
        }
    }
    
    private var loadingView: some View {
        VStack {
            ProgressView()
                .progressViewStyle(.circular)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
    
    private var emptyStateView: some View {
        VStack(spacing: Space.md) {
            Image(systemName: "calendar.badge.plus")
                .font(.system(size: 48))
                .foregroundColor(Color.textTertiary)
            
            Text("No routines yet")
                .font(.system(size: 17, weight: .semibold))
                .foregroundColor(Color.textPrimary)
            
            Text("Use the Coach to create your first training program")
                .font(.system(size: 14))
                .foregroundColor(Color.textSecondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, Space.xl)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
    
    private var routinesList: some View {
        ScrollView {
            LazyVStack(spacing: Space.sm) {
                ForEach(routines) { routine in
                    NavigationLink(destination: RoutineDetailView(routineId: routine.id, routineName: routine.name)) {
                        LibraryRoutineRow(routine: routine)
                    }
                    .buttonStyle(PlainButtonStyle())
                }
            }
            .padding(Space.lg)
        }
    }
    
    private func loadRoutines() async {
        // Load from API
        do {
            let fetchedRoutines = try await FocusModeWorkoutService.shared.getUserRoutines()
            routines = fetchedRoutines.map { info in
                RoutineItem(
                    id: info.id,
                    name: info.name,
                    workoutCount: info.workoutCount,
                    isActive: info.isActive
                )
            }
        } catch {
            print("[RoutinesListView] Failed to load routines: \(error)")
        }
        isLoading = false
    }
}

// MARK: - Routine Item Model

struct RoutineItem: Identifiable {
    let id: String
    let name: String
    let workoutCount: Int
    let isActive: Bool
}

// MARK: - Routine Row View

private struct LibraryRoutineRow: View {
    let routine: RoutineItem
    
    var body: some View {
        HStack(spacing: Space.md) {
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: Space.sm) {
                    Text(routine.name)
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundColor(Color.textPrimary)
                    
                    if routine.isActive {
                        Text("Active")
                            .font(.system(size: 11, weight: .medium))
                            .foregroundColor(Color.success)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(Color.success.opacity(0.15))
                            .clipShape(Capsule())
                    }
                }
                
                Text("\(routine.workoutCount) workouts")
                    .font(.system(size: 13))
                    .foregroundColor(Color.textSecondary)
            }
            
            Spacer()
            
            Image(systemName: "chevron.right")
                .font(.system(size: 14, weight: .medium))
                .foregroundColor(Color.textTertiary)
        }
        .padding(Space.md)
        .background(Color.surface)
        .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.medium))
    }
}

// MARK: - Templates List View (Scaffold)

struct TemplatesListView: View {
    @State private var templates: [TemplateItem] = []
    @State private var isLoading = true
    
    var body: some View {
        Group {
            if isLoading {
                loadingView
            } else if templates.isEmpty {
                emptyStateView
            } else {
                templatesList
            }
        }
        .background(Color.bg)
        .navigationTitle("Templates")
        .navigationBarTitleDisplayMode(.large)
        .task {
            await loadTemplates()
        }
    }
    
    private var loadingView: some View {
        VStack {
            ProgressView()
                .progressViewStyle(.circular)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
    
    private var emptyStateView: some View {
        VStack(spacing: Space.md) {
            Image(systemName: "doc.on.doc")
                .font(.system(size: 48))
                .foregroundColor(Color.textTertiary)
            
            Text("No templates yet")
                .font(.system(size: 17, weight: .semibold))
                .foregroundColor(Color.textPrimary)
            
            Text("Templates are saved from completed workouts or created via Coach")
                .font(.system(size: 14))
                .foregroundColor(Color.textSecondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, Space.xl)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
    
    private var templatesList: some View {
        ScrollView {
            LazyVStack(spacing: Space.sm) {
                ForEach(templates) { template in
                    NavigationLink(destination: TemplateDetailView(templateId: template.id, templateName: template.name)) {
                        LibraryTemplateRow(template: template)
                    }
                    .buttonStyle(PlainButtonStyle())
                }
            }
            .padding(Space.lg)
        }
    }
    
    private func loadTemplates() async {
        // Load from FocusModeWorkoutService
        do {
            let fetchedTemplates = try await FocusModeWorkoutService.shared.getUserTemplates()
            templates = fetchedTemplates.map { info in
                TemplateItem(
                    id: info.id,
                    name: info.name,
                    exerciseCount: info.exerciseCount,
                    setCount: info.setCount
                )
            }
        } catch {
            print("[TemplatesListView] Failed to load templates: \(error)")
        }
        isLoading = false
    }
}

// MARK: - Template Item Model

struct TemplateItem: Identifiable {
    let id: String
    let name: String
    let exerciseCount: Int
    let setCount: Int
}

// MARK: - Template Row View

private struct LibraryTemplateRow: View {
    let template: TemplateItem
    
    var body: some View {
        HStack(spacing: Space.md) {
            VStack(alignment: .leading, spacing: 2) {
                Text(template.name)
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(Color.textPrimary)
                
                Text("\(template.exerciseCount) exercises • \(template.setCount) sets")
                    .font(.system(size: 13))
                    .foregroundColor(Color.textSecondary)
            }
            
            Spacer()
            
            Image(systemName: "chevron.right")
                .font(.system(size: 14, weight: .medium))
                .foregroundColor(Color.textTertiary)
        }
        .padding(Space.md)
        .background(Color.surface)
        .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.medium))
    }
}

// MARK: - Exercises List View (Browse Mode)
// Reuses FocusModeExerciseSearch patterns for consistency - loads exercises on open, tap for details

struct ExercisesListView: View {
    @StateObject private var viewModel = ExercisesViewModel()
    
    @State private var searchText = ""
    @State private var filters = ExerciseFilters()
    @State private var showingFilterSheet = false
    @State private var showingExerciseDetail: Exercise?
    
    // Filtered exercises based on current filters
    private var filteredExercises: [Exercise] {
        var result = viewModel.exercises
        
        // Apply muscle group filter
        if !filters.muscleGroups.isEmpty {
            result = result.filter { exercise in
                let exerciseMuscles = Set(exercise.primaryMuscles.map { $0.lowercased() })
                let filterMuscles = Set(filters.muscleGroups.flatMap { group -> [String] in
                    (MuscleGroupMapping(rawValue: group)?.muscles ?? []).map { $0.lowercased() }
                })
                return !exerciseMuscles.isDisjoint(with: filterMuscles)
            }
        }
        
        // Apply equipment filter
        if !filters.equipment.isEmpty {
            result = result.filter { exercise in
                let exerciseEquipSet = Set(exercise.equipment.map { $0.lowercased() })
                return filters.equipment.contains { filterEquip in
                    let lowerFilter = filterEquip.lowercased()
                    return exerciseEquipSet.contains { equip in
                        equip == lowerFilter || equip.contains(lowerFilter) || lowerFilter.contains(equip)
                    }
                }
            }
        }
        
        // Apply movement pattern filter
        if !filters.movementPatterns.isEmpty {
            result = result.filter { exercise in
                let pattern = exercise.movementType.lowercased()
                return filters.movementPatterns.contains { pattern.contains($0.lowercased()) }
            }
        }
        
        // Apply difficulty filter
        if !filters.difficulty.isEmpty {
            result = result.filter { exercise in
                filters.difficulty.contains(exercise.level.capitalized)
            }
        }
        
        return result
    }
    
    var body: some View {
        VStack(spacing: 0) {
            // Search bar with filter button
            searchAndFilterBar
            
            // Exercise list
            if viewModel.isLoading {
                loadingView
            } else if filteredExercises.isEmpty {
                emptyView
            } else {
                exerciseList
            }
        }
        .background(Color.bg)
        .navigationTitle("Exercises")
        .navigationBarTitleDisplayMode(.large)
        .task {
            await viewModel.loadExercises()
        }
        .onChange(of: searchText) { _, newValue in
            Task {
                await viewModel.searchExercises(query: newValue)
            }
        }
        .sheet(isPresented: $showingFilterSheet) {
            ExerciseFilterSheet(
                filters: $filters,
                onApply: { showingFilterSheet = false },
                onClear: {
                    filters.clear()
                    showingFilterSheet = false
                }
            )
        }
        .sheet(item: $showingExerciseDetail) { exercise in
            FocusModeExerciseDetailSheet(exercise: exercise)
        }
    }
    
    // MARK: - Search and Filter Bar
    
    private var searchAndFilterBar: some View {
        VStack(spacing: Space.sm) {
            HStack(spacing: Space.sm) {
                // Search field
                HStack(spacing: Space.sm) {
                    Image(systemName: "magnifyingglass")
                        .foregroundColor(Color.textSecondary)
                    
                    TextField("Search exercises...", text: $searchText)
                        .textFieldStyle(PlainTextFieldStyle())
                        .font(.system(size: 16))
                        .autocorrectionDisabled()
                        .textInputAutocapitalization(.never)
                    
                    if !searchText.isEmpty {
                        Button {
                            searchText = ""
                        } label: {
                            Image(systemName: "xmark.circle.fill")
                                .foregroundColor(Color.textSecondary)
                        }
                    }
                }
                .padding(.horizontal, Space.md)
                .padding(.vertical, 12)
                .background(Color.surface)
                .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.medium))
                
                // Filter button
                Button {
                    showingFilterSheet = true
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "line.3.horizontal.decrease")
                            .font(.system(size: 14, weight: .medium))
                        
                        if filters.activeCount > 0 {
                            Text("·")
                            Text("\(filters.activeCount)")
                                .font(.system(size: 13, weight: .semibold).monospacedDigit())
                        }
                    }
                    .foregroundColor(filters.isEmpty ? Color.textSecondary : Color.accent)
                    .padding(.horizontal, Space.md)
                    .padding(.vertical, 12)
                    .background(filters.isEmpty ? Color.surface : Color.accent.opacity(0.12))
                    .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.medium))
                    .overlay(
                        RoundedRectangle(cornerRadius: CornerRadiusToken.medium)
                            .stroke(filters.isEmpty ? Color.clear : Color.accent.opacity(0.3), lineWidth: 1)
                    )
                }
                .buttonStyle(PlainButtonStyle())
            }
            .padding(.horizontal, Space.md)
            .padding(.top, Space.sm)
            
            // Active filter pills (quick dismissal)
            if !filters.isEmpty {
                activeFilterPills
            }
        }
        .padding(.bottom, Space.sm)
        .background(Color.bg)
    }
    
    // MARK: - Active Filter Pills
    
    private var activeFilterPills: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: Space.sm) {
                // Clear all
                Button {
                    filters.clear()
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "xmark")
                            .font(.system(size: 10, weight: .bold))
                        Text("Clear all")
                            .font(.system(size: 12, weight: .medium))
                    }
                    .foregroundColor(Color.textSecondary)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(Color.surfaceElevated)
                    .clipShape(Capsule())
                }
                .buttonStyle(PlainButtonStyle())
                
                // Muscle groups
                ForEach(Array(filters.muscleGroups), id: \.self) { group in
                    activeFilterPill(label: group, color: Color.accent) {
                        filters.muscleGroups.remove(group)
                    }
                }
                
                // Equipment
                ForEach(Array(filters.equipment), id: \.self) { equip in
                    activeFilterPill(label: equip, color: Color.accent) {
                        filters.equipment.remove(equip)
                    }
                }
                
                // Movement patterns
                ForEach(Array(filters.movementPatterns), id: \.self) { pattern in
                    activeFilterPill(label: pattern, color: Color.warning) {
                        filters.movementPatterns.remove(pattern)
                    }
                }
            }
            .padding(.horizontal, Space.md)
        }
    }
    
    private func activeFilterPill(label: String, color: Color, onRemove: @escaping () -> Void) -> some View {
        HStack(spacing: 4) {
            Text(label)
                .font(.system(size: 12, weight: .medium))
            
            Button(action: onRemove) {
                Image(systemName: "xmark")
                    .font(.system(size: 9, weight: .bold))
            }
        }
        .foregroundColor(color)
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .background(color.opacity(0.12))
        .clipShape(Capsule())
    }
    
    // MARK: - Exercise List
    
    private var exerciseList: some View {
        ScrollView {
            LazyVStack(spacing: 0) {
                // Results count
                HStack {
                    Text("\(filteredExercises.count) exercises")
                        .font(.system(size: 13))
                        .foregroundColor(Color.textTertiary)
                    Spacer()
                }
                .padding(.horizontal, Space.md)
                .padding(.vertical, Space.sm)
                
                ForEach(filteredExercises) { exercise in
                    LibraryExerciseRow(
                        exercise: exercise,
                        onTap: {
                            showingExerciseDetail = exercise
                        }
                    )
                    
                    Divider()
                        .padding(.leading, Space.md)
                }
            }
            .padding(.bottom, Space.xl)
        }
    }
    
    // MARK: - Loading View
    
    private var loadingView: some View {
        VStack {
            Spacer()
            ProgressView()
                .scaleEffect(1.2)
            Text("Loading exercises...")
                .font(.system(size: 14))
                .foregroundColor(Color.textSecondary)
                .padding(.top, Space.md)
            Spacer()
        }
    }
    
    // MARK: - Empty View
    
    private var emptyView: some View {
        VStack(spacing: Space.md) {
            Spacer()
            
            Image(systemName: "magnifyingglass")
                .font(.system(size: 32))
                .foregroundColor(Color.textTertiary)
            
            Text("No exercises found")
                .font(.system(size: 16, weight: .medium))
                .foregroundColor(Color.textSecondary)
            
            if !searchText.isEmpty {
                Text("Try a different search term")
                    .font(.system(size: 14))
                    .foregroundColor(Color.textTertiary)
            }
            
            if !filters.isEmpty {
                Button {
                    filters.clear()
                } label: {
                    Text("Clear all filters")
                        .font(.system(size: 14, weight: .medium))
                        .foregroundColor(Color.accent)
                }
                .padding(.top, Space.sm)
            }
            
            Spacer()
        }
    }
}

// MARK: - Library Exercise Row (Browse Mode - No Add Button)

private struct LibraryExerciseRow: View {
    let exercise: Exercise
    let onTap: () -> Void
    
    var body: some View {
        Button(action: onTap) {
            HStack(spacing: Space.md) {
                // Exercise info
                VStack(alignment: .leading, spacing: 2) {
                    Text(exercise.capitalizedName)
                        .font(.system(size: 15, weight: .medium))
                        .foregroundColor(Color.textPrimary)
                        .lineLimit(1)
                    
                    Text(exerciseSubtitle)
                        .font(.system(size: 13))
                        .foregroundColor(Color.textSecondary)
                        .lineLimit(1)
                }
                
                Spacer()
                
                // Chevron for detail navigation
                Image(systemName: "chevron.right")
                    .font(.system(size: 14, weight: .medium))
                    .foregroundColor(Color.textTertiary)
            }
            .padding(.horizontal, Space.md)
            .padding(.vertical, 12)
            .background(Color.surface)
            .contentShape(Rectangle())
        }
        .buttonStyle(PlainButtonStyle())
    }
    
    private var exerciseSubtitle: String {
        let muscles = exercise.capitalizedPrimaryMuscles.joined(separator: ", ")
        let equipment = exercise.capitalizedEquipment
        
        if !muscles.isEmpty && !equipment.isEmpty {
            return "\(muscles) • \(equipment)"
        } else if !muscles.isEmpty {
            return muscles
        } else if !equipment.isEmpty {
            return equipment
        }
        return ""
    }
}

// MARK: - Template Detail View (Reuses ExerciseRowView from Canvas)

struct TemplateDetailView: View {
    let templateId: String
    let templateName: String
    
    @State private var template: WorkoutTemplate?
    @State private var planExercises: [PlanExercise] = []
    @State private var isLoading = true
    
    // State for ExerciseRowView
    @State private var expandedExerciseId: String? = nil
    @State private var selectedCell: GridCellField? = nil
    @State private var warmupCollapsed: [String: Bool] = [:]
    @State private var selectedExerciseForInfo: PlanExercise? = nil
    @State private var exerciseForSwap: PlanExercise? = nil
    
    var body: some View {
        Group {
            if isLoading {
                loadingView
            } else if !planExercises.isEmpty {
                templateContent
            } else {
                errorView
            }
        }
        .background(Color.bg)
        .navigationTitle(templateName)
        .navigationBarTitleDisplayMode(.inline)
        .task {
            await loadTemplate()
        }
        .sheet(item: $selectedExerciseForInfo) { exercise in
            ExerciseDetailSheet(
                exerciseId: exercise.exerciseId,
                exerciseName: exercise.name,
                onDismiss: { selectedExerciseForInfo = nil }
            )
        }
        .sheet(item: $exerciseForSwap) { exercise in
            ExerciseSwapSheet(
                currentExercise: exercise,
                onSwapWithAI: { _, _ in /* No AI swap in library mode */ },
                onSwapManual: { replacement in
                    handleManualSwap(exercise: exercise, with: replacement)
                },
                onDismiss: { exerciseForSwap = nil }
            )
        }
    }
    
    private var loadingView: some View {
        VStack {
            ProgressView()
                .progressViewStyle(.circular)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
    
    private var errorView: some View {
        VStack(spacing: Space.md) {
            Image(systemName: "exclamationmark.triangle")
                .font(.system(size: 48))
                .foregroundColor(Color.warning)
            
            Text("Template not found")
                .font(.system(size: 17, weight: .semibold))
                .foregroundColor(Color.textPrimary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
    
    private var templateContent: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                // Header stats
                headerStats
                    .padding(Space.lg)
                
                // Divider
                Rectangle()
                    .fill(Color.separatorLine)
                    .frame(height: 1)
                
                // Exercises list using ExerciseRowView
                exercisesList
            }
        }
    }
    
    private var headerStats: some View {
        HStack(spacing: Space.lg) {
            templateStat(value: "\(planExercises.count)", label: "Exercises")
            templateStat(value: "\(planExercises.reduce(0) { $0 + $1.sets.count })", label: "Sets")
            
            if let duration = template?.analytics?.estimatedDuration, duration > 0 {
                templateStat(value: "~\(duration)", label: "min")
            }
        }
    }
    
    private func templateStat(value: String, label: String) -> some View {
        VStack(spacing: 2) {
            Text(value)
                .font(.system(size: 24, weight: .bold))
                .foregroundColor(Color.textPrimary)
            Text(label)
                .font(.system(size: 13))
                .foregroundColor(Color.textSecondary)
        }
    }
    
    private var exercisesList: some View {
        VStack(spacing: 0) {
            ForEach(Array(planExercises.indices), id: \.self) { index in
                let exercise = planExercises[index]
                let isExpanded = expandedExerciseId == exercise.id
                
                ExerciseRowView(
                    exerciseIndex: index,
                    exercises: $planExercises,
                    selectedCell: $selectedCell,
                    isExpanded: isExpanded,
                    isPlanningMode: true,  // Library templates are editable
                    showDivider: index < planExercises.count - 1,
                    onToggleExpand: {
                        withAnimation(.easeInOut(duration: 0.2)) {
                            expandedExerciseId = isExpanded ? nil : exercise.id
                        }
                    },
                    onSwap: { ex, reason in
                        if reason == .manualSearch {
                            exerciseForSwap = ex
                        }
                        // For library mode, only manual swap is supported
                    },
                    onInfo: { ex in
                        selectedExerciseForInfo = ex
                    },
                    onRemove: { exIdx in
                        withAnimation(.easeOut(duration: 0.2)) {
                            _ = planExercises.remove(at: exIdx)
                        }
                    },
                    warmupCollapsed: Binding(
                        get: { warmupCollapsed[exercise.id] ?? true },
                        set: { warmupCollapsed[exercise.id] = $0 }
                    )
                )
            }
        }
    }
    
    private func handleManualSwap(exercise: PlanExercise, with replacement: Exercise) {
        if let index = planExercises.firstIndex(where: { $0.id == exercise.id }) {
            let newExercise = PlanExercise(
                exerciseId: replacement.id,
                name: replacement.name,
                sets: exercise.sets,
                primaryMuscles: replacement.primaryMuscles,
                equipment: replacement.equipment.first
            )
            planExercises[index] = newExercise
        }
    }
    
    private func loadTemplate() async {
        do {
            template = try await FocusModeWorkoutService.shared.getTemplate(id: templateId)
            if let template = template {
                planExercises = convertToPlanExercises(template)
            }
        } catch {
            print("[TemplateDetailView] Failed to load template: \(error)")
        }
        isLoading = false
    }
    
    /// Convert WorkoutTemplate to [PlanExercise] for use with ExerciseRowView
    private func convertToPlanExercises(_ template: WorkoutTemplate) -> [PlanExercise] {
        return template.exercises.enumerated().map { index, templateEx in
            let planSets = templateEx.sets.map { templateSet in
                PlanSet(
                    id: templateSet.id,
                    type: SetType(rawValue: templateSet.type) ?? .working,
                    reps: templateSet.reps,
                    weight: templateSet.weight > 0 ? templateSet.weight : nil,
                    rir: templateSet.rir,
                    isLinkedToBase: true
                )
            }
            
            return PlanExercise(
                id: templateEx.id,
                exerciseId: templateEx.exerciseId,
                name: templateEx.name ?? "Exercise",
                sets: planSets,
                primaryMuscles: nil,  // Template doesn't store this
                equipment: nil,
                coachNote: nil,
                position: index,
                restBetweenSets: templateEx.restBetweenSets
            )
        }
    }
}

// MARK: - Routine Detail View

struct RoutineDetailView: View {
    let routineId: String
    let routineName: String
    
    @State private var templates: [TemplateItem] = []
    @State private var isLoading = true
    @State private var routineDescription: String?
    @State private var frequency: Int = 0
    
    var body: some View {
        Group {
            if isLoading {
                loadingView
            } else if templates.isEmpty {
                emptyView
            } else {
                routineContent
            }
        }
        .background(Color.bg)
        .navigationTitle(routineName)
        .navigationBarTitleDisplayMode(.inline)
        .task {
            await loadRoutineTemplates()
        }
    }
    
    private var loadingView: some View {
        VStack {
            ProgressView()
                .progressViewStyle(.circular)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
    
    private var emptyView: some View {
        VStack(spacing: Space.md) {
            Image(systemName: "doc.on.doc")
                .font(.system(size: 48))
                .foregroundColor(Color.textTertiary)
            
            Text("No workouts in this routine")
                .font(.system(size: 17, weight: .semibold))
                .foregroundColor(Color.textPrimary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
    
    private var routineContent: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Space.lg) {
                // Header with routine info
                VStack(alignment: .leading, spacing: Space.sm) {
                    HStack(spacing: Space.lg) {
                        routineStat(value: "\(templates.count)", label: "Workouts")
                        routineStat(value: "\(frequency)x", label: "Per Week")
                    }
                    
                    if let description = routineDescription, !description.isEmpty {
                        Text(description)
                            .font(.system(size: 14))
                            .foregroundColor(Color.textSecondary)
                    }
                }
                .padding(.horizontal, Space.lg)
                .padding(.top, Space.md)
                
                // Templates list
                VStack(spacing: Space.sm) {
                    ForEach(Array(templates.enumerated()), id: \.element.id) { index, template in
                        NavigationLink(destination: TemplateDetailView(templateId: template.id, templateName: template.name)) {
                            routineTemplateRow(template, dayNumber: index + 1)
                        }
                        .buttonStyle(PlainButtonStyle())
                    }
                }
                .padding(.horizontal, Space.lg)
                
                Spacer(minLength: Space.xxl)
            }
        }
    }
    
    private func routineStat(value: String, label: String) -> some View {
        VStack(spacing: 2) {
            Text(value)
                .font(.system(size: 24, weight: .bold))
                .foregroundColor(Color.textPrimary)
            Text(label)
                .font(.system(size: 13))
                .foregroundColor(Color.textSecondary)
        }
    }
    
    private func routineTemplateRow(_ template: TemplateItem, dayNumber: Int) -> some View {
        HStack(spacing: Space.md) {
            // Day badge
            Text("Day \(dayNumber)")
                .font(.system(size: 12, weight: .semibold))
                .foregroundColor(Color.accent)
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(Color.accent.opacity(0.12))
                .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.small))
            
            VStack(alignment: .leading, spacing: 2) {
                Text(template.name)
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(Color.textPrimary)
                
                Text("\(template.exerciseCount) exercises • \(template.setCount) sets")
                    .font(.system(size: 13))
                    .foregroundColor(Color.textSecondary)
            }
            
            Spacer()
            
            Image(systemName: "chevron.right")
                .font(.system(size: 14, weight: .medium))
                .foregroundColor(Color.textTertiary)
        }
        .padding(Space.md)
        .background(Color.surface)
        .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.medium))
    }
    
    private func loadRoutineTemplates() async {
        // For now, load all templates - in a future version we'd have a getRoutine API
        // that returns the routine with its template_ids which we'd then fetch
        do {
            let fetchedTemplates = try await FocusModeWorkoutService.shared.getUserTemplates()
            templates = fetchedTemplates.map { info in
                TemplateItem(
                    id: info.id,
                    name: info.name,
                    exerciseCount: info.exerciseCount,
                    setCount: info.setCount
                )
            }
            
            // Use the template count as a proxy for frequency (usually matches)
            frequency = min(templates.count, 6)  // Cap at 6x per week
        } catch {
            print("[RoutineDetailView] Failed to load templates: \(error)")
        }
        isLoading = false
    }
}

#if DEBUG
struct LibraryView_Previews: PreviewProvider {
    static var previews: some View {
        NavigationStack {
            LibraryView()
        }
    }
}
#endif
