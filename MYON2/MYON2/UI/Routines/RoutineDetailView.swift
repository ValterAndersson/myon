import SwiftUI

/// Detail view for a routine - shows workouts in order with drag-to-reorder
struct RoutineDetailView: View {
    @Environment(\.dismiss) private var dismiss
    @StateObject private var viewModel: RoutineDetailViewModel
    @State private var showingEditSheet = false
    @State private var showingTemplateSelector = false
    @State private var showingDeleteConfirmation = false
    
    let onUpdate: () -> Void
    
    init(routine: Routine, onUpdate: @escaping () -> Void) {
        _viewModel = StateObject(wrappedValue: RoutineDetailViewModel(routine: routine))
        self.onUpdate = onUpdate
    }
    
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: Space.lg) {
                    // Header
                    routineHeader
                    
                    // Workouts section
                    workoutsSection
                }
                .padding(Space.lg)
            }
            .background(ColorsToken.Background.secondary)
            .navigationTitle(viewModel.routine.name)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Done") { dismiss() }
                }
                ToolbarItem(placement: .primaryAction) {
                    Menu {
                        if !viewModel.isActive {
                            Button {
                                Task { await viewModel.setAsActive() }
                            } label: {
                                Label("Set as Active", systemImage: "checkmark.circle")
                            }
                        } else {
                            Button {
                                Task { await viewModel.clearActive() }
                            } label: {
                                Label("Deactivate", systemImage: "xmark.circle")
                            }
                        }
                        
                        Button { showingEditSheet = true } label: {
                            Label("Edit Details", systemImage: "pencil")
                        }
                        
                        Divider()
                        
                        Button(role: .destructive) {
                            showingDeleteConfirmation = true
                        } label: {
                            Label("Delete Routine", systemImage: "trash")
                        }
                    } label: {
                        Image(systemName: "ellipsis.circle")
                    }
                }
            }
            .sheet(isPresented: $showingEditSheet) {
                RoutineEditView(mode: .edit(viewModel.routine)) { updated in
                    Task {
                        await viewModel.updateRoutine(updated)
                        onUpdate()
                    }
                }
            }
            .sheet(isPresented: $showingTemplateSelector) {
                TemplatePickerView(selectedIds: viewModel.routine.templateIds) { selectedIds in
                    Task {
                        await viewModel.updateTemplateIds(selectedIds)
                        onUpdate()
                    }
                }
            }
            .confirmationDialog("Delete Routine?", isPresented: $showingDeleteConfirmation, titleVisibility: .visible) {
                Button("Delete", role: .destructive) {
                    Task {
                        await viewModel.deleteRoutine()
                        onUpdate()
                        dismiss()
                    }
                }
                Button("Cancel", role: .cancel) {}
            } message: {
                Text("This will permanently delete the routine. Your workout templates will not be affected.")
            }
            .task {
                await viewModel.loadTemplates()
            }
        }
    }
    
    private var routineHeader: some View {
        VStack(alignment: .leading, spacing: Space.md) {
            // Status badge
            HStack {
                if viewModel.isActive {
                    Label("Active Routine", systemImage: "checkmark.circle.fill")
                        .font(TypographyToken.caption)
                        .foregroundColor(ColorsToken.Brand.primary)
                        .padding(.horizontal, Space.sm)
                        .padding(.vertical, Space.xxs)
                        .background(ColorsToken.Brand.accent100)
                        .cornerRadius(CornerRadiusToken.small)
                }
                
                Spacer()
                
                Text("\(viewModel.routine.frequency)x per week")
                    .font(TypographyToken.subheadline)
                    .foregroundColor(ColorsToken.Text.secondary)
            }
            
            // Description
            if let description = viewModel.routine.description, !description.isEmpty {
                Text(description)
                    .font(TypographyToken.body)
                    .foregroundColor(ColorsToken.Text.secondary)
            }
        }
        .padding(Space.lg)
        .background(ColorsToken.Surface.card)
        .cornerRadius(CornerRadiusToken.medium)
        .shadowStyle(ShadowsToken.level1)
    }
    
    private var workoutsSection: some View {
        VStack(alignment: .leading, spacing: Space.md) {
            HStack {
                Text("Workouts")
                    .font(TypographyToken.headline)
                    .foregroundColor(ColorsToken.Text.primary)
                
                Spacer()
                
                Button {
                    showingTemplateSelector = true
                } label: {
                    Label("Edit", systemImage: "pencil")
                        .font(TypographyToken.subheadline)
                }
            }
            
            if viewModel.templates.isEmpty {
                emptyWorkoutsState
            } else {
                workoutsList
            }
        }
    }
    
    private var emptyWorkoutsState: some View {
        VStack(spacing: Space.md) {
            Image(systemName: "doc.badge.plus")
                .font(.system(size: 32))
                .foregroundColor(ColorsToken.Neutral.n400)
            
            Text("No workouts in this routine")
                .font(TypographyToken.subheadline)
                .foregroundColor(ColorsToken.Text.secondary)
            
            Button {
                showingTemplateSelector = true
            } label: {
                Label("Add Workouts", systemImage: "plus")
                    .font(TypographyToken.button)
            }
            .buttonStyle(.borderedProminent)
            .tint(ColorsToken.Brand.primary)
        }
        .frame(maxWidth: .infinity)
        .padding(Space.xl)
        .background(ColorsToken.Surface.card)
        .cornerRadius(CornerRadiusToken.medium)
        .shadowStyle(ShadowsToken.level1)
    }
    
    private var workoutsList: some View {
        VStack(spacing: Space.sm) {
            ForEach(Array(viewModel.templates.enumerated()), id: \.element.id) { index, template in
                WorkoutDayRow(
                    dayNumber: index + 1,
                    template: template,
                    isNext: viewModel.isNextWorkout(template)
                )
            }
        }
    }
}

// MARK: - Workout Day Row

struct WorkoutDayRow: View {
    let dayNumber: Int
    let template: WorkoutTemplate
    let isNext: Bool
    
    var body: some View {
        HStack(spacing: Space.md) {
            // Day indicator
            ZStack {
                Circle()
                    .fill(isNext ? ColorsToken.Brand.primary : ColorsToken.Neutral.n200)
                    .frame(width: 32, height: 32)
                
                Text("\(dayNumber)")
                    .font(TypographyToken.headline)
                    .foregroundColor(isNext ? .white : ColorsToken.Text.secondary)
            }
            
            VStack(alignment: .leading, spacing: Space.xxs) {
                HStack {
                    Text(template.name)
                        .font(TypographyToken.headline)
                        .foregroundColor(ColorsToken.Text.primary)
                    
                    if isNext {
                        Text("NEXT")
                            .font(.system(size: 10, weight: .bold))
                            .foregroundColor(ColorsToken.Brand.primary)
                            .padding(.horizontal, Space.xs)
                            .padding(.vertical, 2)
                            .background(ColorsToken.Brand.accent100)
                            .cornerRadius(CornerRadiusToken.small)
                    }
                }
                
                // Exercise count and duration
                HStack(spacing: Space.sm) {
                    Label("\(template.exercises.count) exercises", systemImage: "dumbbell")
                        .font(TypographyToken.caption)
                        .foregroundColor(ColorsToken.Text.secondary)
                    
                    if let duration = template.analytics?.estimatedDuration {
                        Label("\(duration) min", systemImage: "clock")
                            .font(TypographyToken.caption)
                            .foregroundColor(ColorsToken.Text.secondary)
                    }
                }
            }
            
            Spacer()
            
            Image(systemName: "chevron.right")
                .font(.system(size: IconSizeToken.sm))
                .foregroundColor(ColorsToken.Neutral.n400)
        }
        .padding(Space.md)
        .background(ColorsToken.Surface.card)
        .cornerRadius(CornerRadiusToken.medium)
        .shadowStyle(ShadowsToken.level1)
    }
}

// MARK: - ViewModel

@MainActor
class RoutineDetailViewModel: ObservableObject {
    @Published var routine: Routine
    @Published var templates: [WorkoutTemplate] = []
    @Published var isActive = false
    @Published var isLoading = false
    @Published var error: String?
    
    private let routineRepository: RoutineRepositoryProtocol
    private let templateRepository: TemplateRepositoryProtocol
    private let authService: AuthService
    
    init(
        routine: Routine,
        routineRepository: RoutineRepositoryProtocol = RoutineRepository(),
        templateRepository: TemplateRepositoryProtocol = TemplateRepository(),
        authService: AuthService = .shared
    ) {
        self.routine = routine
        self.routineRepository = routineRepository
        self.templateRepository = templateRepository
        self.authService = authService
    }
    
    private var userId: String? { authService.currentUserId }
    
    func loadTemplates() async {
        guard let userId = userId else { return }
        
        isLoading = true
        do {
            // Check if active
            if let active = try await routineRepository.getActiveRoutine(userId: userId) {
                isActive = active.id == routine.id
            }
            
            // Load templates
            let allTemplates = try await templateRepository.getTemplates(userId: userId)
            templates = routine.templateIds.compactMap { id in
                allTemplates.first { $0.id == id }
            }
        } catch {
            self.error = error.localizedDescription
        }
        isLoading = false
    }
    
    func isNextWorkout(_ template: WorkoutTemplate) -> Bool {
        // Simple logic: first template is next (can be enhanced with cursor later)
        templates.first?.id == template.id
    }
    
    func setAsActive() async {
        guard let userId = userId else { return }
        
        do {
            try await routineRepository.setActiveRoutine(routineId: routine.id, userId: userId)
            isActive = true
        } catch {
            self.error = error.localizedDescription
        }
    }
    
    func clearActive() async {
        guard let userId = userId else { return }
        
        do {
            try await routineRepository.setActiveRoutine(routineId: "", userId: userId)
            isActive = false
        } catch {
            self.error = error.localizedDescription
        }
    }
    
    func updateRoutine(_ updated: Routine) async {
        do {
            try await routineRepository.updateRoutine(updated)
            routine = updated
        } catch {
            self.error = error.localizedDescription
        }
    }
    
    func updateTemplateIds(_ ids: [String]) async {
        var updated = routine
        updated.templateIds = ids
        await updateRoutine(updated)
        await loadTemplates()
    }
    
    func deleteRoutine() async {
        guard let userId = userId else { return }
        
        do {
            try await routineRepository.deleteRoutine(id: routine.id, userId: userId)
        } catch {
            self.error = error.localizedDescription
        }
    }
}

// MARK: - Preview

#Preview {
    RoutineDetailView(
        routine: Routine(
            id: "1",
            userId: "user1",
            name: "Push Pull Legs",
            description: "Classic 3-day split focusing on compound movements",
            templateIds: [],
            frequency: 3,
            createdAt: Date(),
            updatedAt: Date()
        )
    ) {}
}
