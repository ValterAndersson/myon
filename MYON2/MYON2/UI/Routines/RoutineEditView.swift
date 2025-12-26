import SwiftUI

/// Edit view for creating or modifying a routine
struct RoutineEditView: View {
    @Environment(\.dismiss) private var dismiss
    
    enum Mode {
        case create
        case edit(Routine)
    }
    
    let mode: Mode
    let onSave: (Routine) -> Void
    
    @State private var name: String
    @State private var description: String
    @State private var frequency: Int
    @State private var templateIds: [String]
    @State private var isSaving = false
    
    private let authService = AuthService.shared
    
    init(mode: Mode, onSave: @escaping (Routine) -> Void) {
        self.mode = mode
        self.onSave = onSave
        
        switch mode {
        case .create:
            _name = State(initialValue: "")
            _description = State(initialValue: "")
            _frequency = State(initialValue: 3)
            _templateIds = State(initialValue: [])
        case .edit(let routine):
            _name = State(initialValue: routine.name)
            _description = State(initialValue: routine.description ?? "")
            _frequency = State(initialValue: routine.frequency)
            _templateIds = State(initialValue: routine.templateIds)
        }
    }
    
    private var isValid: Bool {
        !name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }
    
    private var title: String {
        switch mode {
        case .create: return "New Routine"
        case .edit: return "Edit Routine"
        }
    }
    
    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("Routine Name", text: $name)
                        .font(TypographyToken.body)
                    
                    TextField("Description (optional)", text: $description, axis: .vertical)
                        .font(TypographyToken.body)
                        .lineLimit(3...6)
                } header: {
                    Text("Details")
                }
                
                Section {
                    Stepper(value: $frequency, in: 1...7) {
                        HStack {
                            Text("Frequency")
                                .font(TypographyToken.body)
                            Spacer()
                            Text("\(frequency)x per week")
                                .font(TypographyToken.body)
                                .foregroundColor(ColorsToken.Text.secondary)
                        }
                    }
                } header: {
                    Text("Schedule")
                } footer: {
                    Text("How many times per week you plan to train with this routine.")
                        .font(TypographyToken.caption)
                        .foregroundColor(ColorsToken.Text.muted)
                }
            }
            .navigationTitle(title)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        saveRoutine()
                    }
                    .disabled(!isValid || isSaving)
                }
            }
        }
    }
    
    private func saveRoutine() {
        guard let userId = authService.currentUser?.uid else { return }
        
        isSaving = true
        
        let routine: Routine
        switch mode {
        case .create:
            routine = Routine(
                id: UUID().uuidString,
                userId: userId,
                name: name.trimmingCharacters(in: .whitespacesAndNewlines),
                description: description.isEmpty ? nil : description,
                templateIds: templateIds,
                frequency: frequency,
                createdAt: Date(),
                updatedAt: Date()
            )
        case .edit(let existing):
            routine = Routine(
                id: existing.id,
                userId: existing.userId,
                name: name.trimmingCharacters(in: .whitespacesAndNewlines),
                description: description.isEmpty ? nil : description,
                templateIds: existing.templateIds,
                frequency: frequency,
                createdAt: existing.createdAt,
                updatedAt: Date()
            )
        }
        
        onSave(routine)
        dismiss()
    }
}

// MARK: - Template Picker View

struct TemplatePickerView: View {
    @Environment(\.dismiss) private var dismiss
    @StateObject private var viewModel = TemplatePickerViewModel()
    
    let initialSelectedIds: [String]
    let onSave: ([String]) -> Void
    
    @State private var selectedIds: [String]
    
    init(selectedIds: [String], onSave: @escaping ([String]) -> Void) {
        self.initialSelectedIds = selectedIds
        self.onSave = onSave
        _selectedIds = State(initialValue: selectedIds)
    }
    
    var body: some View {
        NavigationStack {
            Group {
                if viewModel.isLoading {
                    ProgressView("Loading templates...")
                } else if viewModel.templates.isEmpty {
                    emptyState
                } else {
                    templatesList
                }
            }
            .navigationTitle("Select Workouts")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        onSave(selectedIds)
                        dismiss()
                    }
                }
            }
            .task {
                await viewModel.loadTemplates()
            }
        }
    }
    
    private var emptyState: some View {
        VStack(spacing: Space.lg) {
            Image(systemName: "doc.text")
                .font(.system(size: 48))
                .foregroundColor(ColorsToken.Neutral.n400)
            
            Text("No Templates Yet")
                .font(TypographyToken.title3)
                .foregroundColor(ColorsToken.Text.primary)
            
            Text("Create workout templates first, then add them to your routine.")
                .font(TypographyToken.body)
                .foregroundColor(ColorsToken.Text.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, Space.xl)
        }
        .padding(Space.xl)
    }
    
    private var templatesList: some View {
        List {
            Section {
                // Selected templates (ordered)
                ForEach(selectedIds, id: \.self) { id in
                    if let template = viewModel.templates.first(where: { $0.id == id }) {
                        TemplateSelectRow(template: template, isSelected: true) {
                            selectedIds.removeAll { $0 == id }
                        }
                    }
                }
                .onMove { from, to in
                    selectedIds.move(fromOffsets: from, toOffset: to)
                }
            } header: {
                HStack {
                    Text("In Routine (\(selectedIds.count))")
                    Spacer()
                    if !selectedIds.isEmpty {
                        Text("Drag to reorder")
                            .font(TypographyToken.caption)
                            .foregroundColor(ColorsToken.Text.muted)
                    }
                }
            }
            
            Section {
                // Available templates (not selected)
                let availableTemplates = viewModel.templates.filter { !selectedIds.contains($0.id) }
                ForEach(availableTemplates) { template in
                    TemplateSelectRow(template: template, isSelected: false) {
                        selectedIds.append(template.id)
                    }
                }
            } header: {
                Text("Available Templates")
            }
        }
        .listStyle(.insetGrouped)
        .environment(\.editMode, .constant(.active))
    }
}

// MARK: - Template Select Row

struct TemplateSelectRow: View {
    let template: WorkoutTemplate
    let isSelected: Bool
    let onTap: () -> Void
    
    var body: some View {
        Button(action: onTap) {
            HStack(spacing: Space.md) {
                Image(systemName: isSelected ? "checkmark.circle.fill" : "circle")
                    .font(.system(size: IconSizeToken.lg))
                    .foregroundColor(isSelected ? ColorsToken.Brand.primary : ColorsToken.Neutral.n400)
                
                VStack(alignment: .leading, spacing: Space.xxs) {
                    Text(template.name)
                        .font(TypographyToken.headline)
                        .foregroundColor(ColorsToken.Text.primary)
                    
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
            }
        }
        .buttonStyle(.plain)
    }
}

// MARK: - ViewModel

@MainActor
class TemplatePickerViewModel: ObservableObject {
    @Published var templates: [WorkoutTemplate] = []
    @Published var isLoading = false
    @Published var error: String?
    
    private let templateRepository: TemplateRepositoryProtocol
    private let authService: AuthService
    
    init(
        templateRepository: TemplateRepositoryProtocol = TemplateRepository(),
        authService: AuthService = .shared
    ) {
        self.templateRepository = templateRepository
        self.authService = authService
    }
    
    func loadTemplates() async {
        guard let userId = authService.currentUser?.uid else { return }
        
        isLoading = true
        do {
            templates = try await templateRepository.getTemplates(userId: userId)
        } catch {
            self.error = error.localizedDescription
        }
        isLoading = false
    }
}

// MARK: - Previews

#Preview("Create") {
    RoutineEditView(mode: .create) { _ in }
}

#Preview("Template Picker") {
    TemplatePickerView(selectedIds: []) { _ in }
}
