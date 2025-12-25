import SwiftUI

/// Detail view for a template - shows exercises with expandable set editing
struct TemplateDetailView: View {
    @Environment(\.dismiss) private var dismiss
    @StateObject private var viewModel: TemplateDetailViewModel
    @State private var showingDeleteConfirmation = false
    @State private var editingName = false
    
    let onUpdate: () -> Void
    
    init(template: WorkoutTemplate, onUpdate: @escaping () -> Void) {
        _viewModel = StateObject(wrappedValue: TemplateDetailViewModel(template: template))
        self.onUpdate = onUpdate
    }
    
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: Space.lg) {
                    // Header
                    templateHeader
                    
                    // Exercises
                    exercisesSection
                }
                .padding(Space.lg)
            }
            .background(ColorsToken.Background.secondary)
            .navigationTitle("Template")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Done") {
                        if viewModel.hasChanges {
                            Task {
                                await viewModel.save()
                                onUpdate()
                            }
                        }
                        dismiss()
                    }
                }
                ToolbarItem(placement: .primaryAction) {
                    Menu {
                        Button(role: .destructive) {
                            showingDeleteConfirmation = true
                        } label: {
                            Label("Delete Template", systemImage: "trash")
                        }
                    } label: {
                        Image(systemName: "ellipsis.circle")
                    }
                }
            }
            .confirmationDialog("Delete Template?", isPresented: $showingDeleteConfirmation, titleVisibility: .visible) {
                Button("Delete", role: .destructive) {
                    Task {
                        await viewModel.delete()
                        onUpdate()
                        dismiss()
                    }
                }
                Button("Cancel", role: .cancel) {}
            } message: {
                Text("This will permanently delete the template. Routines using this template will be affected.")
            }
            .alert("Error", isPresented: .constant(viewModel.error != nil)) {
                Button("OK") { viewModel.error = nil }
            } message: {
                Text(viewModel.error ?? "")
            }
        }
    }
    
    private var templateHeader: some View {
        VStack(alignment: .leading, spacing: Space.md) {
            // Editable name
            if editingName {
                HStack {
                    TextField("Template Name", text: $viewModel.name)
                        .font(TypographyToken.title2)
                        .textFieldStyle(.plain)
                    
                    Button("Done") {
                        editingName = false
                    }
                    .font(TypographyToken.subheadline)
                }
            } else {
                HStack {
                    Text(viewModel.name)
                        .font(TypographyToken.title2)
                        .foregroundColor(ColorsToken.Text.primary)
                    
                    Spacer()
                    
                    Button {
                        editingName = true
                    } label: {
                        Image(systemName: "pencil")
                            .font(.system(size: IconSizeToken.sm))
                            .foregroundColor(ColorsToken.Text.secondary)
                    }
                }
            }
            
            // Stats
            if let analytics = viewModel.template.analytics {
                HStack(spacing: Space.md) {
                    StatBadge(label: "\(analytics.totalSets) sets", icon: "list.number")
                    StatBadge(label: "\(analytics.totalReps) reps", icon: "repeat")
                    if let duration = analytics.estimatedDuration {
                        StatBadge(label: "\(duration) min", icon: "clock")
                    }
                }
            }
        }
        .padding(Space.lg)
        .background(ColorsToken.Surface.card)
        .cornerRadius(CornerRadiusToken.medium)
        .shadowStyle(ShadowsToken.level1)
    }
    
    private var exercisesSection: some View {
        VStack(alignment: .leading, spacing: Space.md) {
            Text("Exercises")
                .font(TypographyToken.headline)
                .foregroundColor(ColorsToken.Text.primary)
            
            ForEach(Array(viewModel.exercises.enumerated()), id: \.element.id) { index, exercise in
                ExerciseEditCard(
                    exercise: $viewModel.exercises[index],
                    exerciseNumber: index + 1,
                    onDelete: {
                        viewModel.deleteExercise(at: index)
                    }
                )
            }
        }
    }
}

// MARK: - Stat Badge

struct StatBadge: View {
    let label: String
    let icon: String
    
    var body: some View {
        Label(label, systemImage: icon)
            .font(TypographyToken.caption)
            .foregroundColor(ColorsToken.Text.secondary)
            .padding(.horizontal, Space.sm)
            .padding(.vertical, Space.xxs)
            .background(ColorsToken.Neutral.n100)
            .cornerRadius(CornerRadiusToken.small)
    }
}

// MARK: - Exercise Edit Card

struct ExerciseEditCard: View {
    @Binding var exercise: WorkoutTemplateExercise
    let exerciseNumber: Int
    let onDelete: () -> Void
    
    @State private var isExpanded = false
    
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Header
            Button {
                withAnimation(.easeInOut(duration: MotionToken.medium)) {
                    isExpanded.toggle()
                }
            } label: {
                HStack {
                    // Exercise number
                    Text("\(exerciseNumber)")
                        .font(TypographyToken.headline)
                        .foregroundColor(ColorsToken.Text.secondary)
                        .frame(width: 24)
                    
                    VStack(alignment: .leading, spacing: Space.xxs) {
                        Text(exercise.exerciseId.replacingOccurrences(of: "-", with: " ").capitalized)
                            .font(TypographyToken.headline)
                            .foregroundColor(ColorsToken.Text.primary)
                        
                        Text("\(exercise.sets.count) sets")
                            .font(TypographyToken.caption)
                            .foregroundColor(ColorsToken.Text.secondary)
                    }
                    
                    Spacer()
                    
                    Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                        .font(.system(size: IconSizeToken.sm))
                        .foregroundColor(ColorsToken.Neutral.n400)
                }
                .padding(Space.md)
            }
            .buttonStyle(.plain)
            
            // Expanded sets
            if isExpanded {
                Divider()
                    .background(ColorsToken.Separator.hairline)
                
                VStack(spacing: Space.xs) {
                    // Header row
                    HStack(spacing: Space.sm) {
                        Text("Set")
                            .frame(width: 40)
                        Text("Weight")
                            .frame(width: 70)
                        Text("Reps")
                            .frame(width: 50)
                        Text("RIR")
                            .frame(width: 40)
                        Spacer()
                    }
                    .font(TypographyToken.caption)
                    .foregroundColor(ColorsToken.Text.muted)
                    .padding(.horizontal, Space.md)
                    .padding(.top, Space.sm)
                    
                    ForEach(Array(exercise.sets.enumerated()), id: \.element.id) { index, set in
                        SetEditRow(
                            set: $exercise.sets[index],
                            setNumber: index + 1
                        )
                    }
                    
                    // Add/remove set buttons
                    HStack {
                        Button {
                            addSet()
                        } label: {
                            Label("Add Set", systemImage: "plus.circle")
                                .font(TypographyToken.caption)
                        }
                        
                        Spacer()
                        
                        if exercise.sets.count > 1 {
                            Button(role: .destructive) {
                                removeLastSet()
                            } label: {
                                Label("Remove", systemImage: "minus.circle")
                                    .font(TypographyToken.caption)
                            }
                        }
                    }
                    .padding(.horizontal, Space.md)
                    .padding(.vertical, Space.sm)
                }
            }
        }
        .background(ColorsToken.Surface.card)
        .cornerRadius(CornerRadiusToken.medium)
        .shadowStyle(ShadowsToken.level1)
    }
    
    private func addSet() {
        let lastSet = exercise.sets.last ?? WorkoutTemplateSet(
            id: UUID().uuidString,
            reps: 10,
            rir: 2,
            type: "working",
            weight: 0
        )
        let newSet = WorkoutTemplateSet(
            id: UUID().uuidString,
            reps: lastSet.reps,
            rir: lastSet.rir,
            type: "working",
            weight: lastSet.weight
        )
        exercise.sets.append(newSet)
    }
    
    private func removeLastSet() {
        guard exercise.sets.count > 1 else { return }
        exercise.sets.removeLast()
    }
}

// MARK: - Set Edit Row

struct SetEditRow: View {
    @Binding var set: WorkoutTemplateSet
    let setNumber: Int
    
    @State private var weightText: String = ""
    @State private var repsText: String = ""
    @State private var rirText: String = ""
    
    var body: some View {
        HStack(spacing: Space.sm) {
            // Set number and type indicator
            Text("\(setNumber)")
                .font(TypographyToken.subheadline)
                .foregroundColor(set.type == "warmup" ? ColorsToken.Neutral.n500 : ColorsToken.Text.primary)
                .frame(width: 40)
            
            // Weight
            TextField("kg", text: $weightText)
                .font(TypographyToken.monospaceSmall)
                .keyboardType(.decimalPad)
                .frame(width: 70)
                .padding(.horizontal, Space.xs)
                .padding(.vertical, Space.xxs)
                .background(ColorsToken.Neutral.n50)
                .cornerRadius(CornerRadiusToken.small)
                .onChange(of: weightText) { _, newValue in
                    if let weight = Double(newValue) {
                        set.weight = weight
                    }
                }
            
            // Reps
            TextField("reps", text: $repsText)
                .font(TypographyToken.monospaceSmall)
                .keyboardType(.numberPad)
                .frame(width: 50)
                .padding(.horizontal, Space.xs)
                .padding(.vertical, Space.xxs)
                .background(ColorsToken.Neutral.n50)
                .cornerRadius(CornerRadiusToken.small)
                .onChange(of: repsText) { _, newValue in
                    if let reps = Int(newValue), reps >= 1, reps <= 30 {
                        set.reps = reps
                    }
                }
            
            // RIR
            TextField("rir", text: $rirText)
                .font(TypographyToken.monospaceSmall)
                .keyboardType(.numberPad)
                .frame(width: 40)
                .padding(.horizontal, Space.xs)
                .padding(.vertical, Space.xxs)
                .background(ColorsToken.Neutral.n50)
                .cornerRadius(CornerRadiusToken.small)
                .onChange(of: rirText) { _, newValue in
                    if let rir = Int(newValue), rir >= 0, rir <= 5 {
                        set.rir = rir
                    }
                }
            
            Spacer()
        }
        .padding(.horizontal, Space.md)
        .padding(.vertical, Space.xs)
        .onAppear {
            weightText = set.weight > 0 ? String(format: "%.1f", set.weight) : ""
            repsText = "\(set.reps)"
            rirText = "\(set.rir)"
        }
    }
}

// MARK: - ViewModel

@MainActor
class TemplateDetailViewModel: ObservableObject {
    @Published var template: WorkoutTemplate
    @Published var name: String
    @Published var exercises: [WorkoutTemplateExercise]
    @Published var isSaving = false
    @Published var error: String?
    
    private let originalTemplate: WorkoutTemplate
    private let templateRepository: TemplateRepositoryProtocol
    private let authService: AuthService
    
    var hasChanges: Bool {
        name != originalTemplate.name ||
        exercises != originalTemplate.exercises
    }
    
    init(
        template: WorkoutTemplate,
        templateRepository: TemplateRepositoryProtocol = TemplateRepository(),
        authService: AuthService = .shared
    ) {
        self.template = template
        self.originalTemplate = template
        self.name = template.name
        self.exercises = template.exercises
        self.templateRepository = templateRepository
        self.authService = authService
    }
    
    private var userId: String? { authService.currentUserId }
    
    func deleteExercise(at index: Int) {
        guard exercises.indices.contains(index) else { return }
        exercises.remove(at: index)
    }
    
    func save() async {
        guard hasChanges else { return }
        
        isSaving = true
        do {
            var updated = template
            updated.name = name
            updated.exercises = exercises
            try await templateRepository.updateTemplate(updated)
            template = updated
        } catch {
            self.error = error.localizedDescription
        }
        isSaving = false
    }
    
    func delete() async {
        guard let userId = userId else { return }
        
        do {
            try await templateRepository.deleteTemplate(id: template.id, userId: userId)
        } catch {
            self.error = error.localizedDescription
        }
    }
}

// MARK: - Preview

#Preview {
    TemplateDetailView(
        template: WorkoutTemplate(
            id: "1",
            userId: "user1",
            name: "Push Day",
            description: nil,
            exercises: [
                WorkoutTemplateExercise(
                    id: "e1",
                    exerciseId: "bench-press",
                    position: 0,
                    sets: [
                        WorkoutTemplateSet(id: "s1", reps: 10, rir: 3, type: "working", weight: 60),
                        WorkoutTemplateSet(id: "s2", reps: 10, rir: 2, type: "working", weight: 60),
                        WorkoutTemplateSet(id: "s3", reps: 10, rir: 1, type: "working", weight: 60),
                    ],
                    restBetweenSets: 90
                )
            ],
            analytics: nil,
            createdAt: Date(),
            updatedAt: Date()
        )
    ) {}
}
