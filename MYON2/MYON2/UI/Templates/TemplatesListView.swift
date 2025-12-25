import SwiftUI

/// Templates library view - shows all user workout templates
struct TemplatesListView: View {
    @StateObject private var viewModel = TemplatesViewModel()
    @State private var selectedTemplate: WorkoutTemplate?
    
    var body: some View {
        NavigationStack {
            Group {
                if viewModel.isLoading && viewModel.templates.isEmpty {
                    loadingView
                } else if viewModel.templates.isEmpty {
                    emptyStateView
                } else {
                    templatesList
                }
            }
            .navigationTitle("Templates")
            .refreshable {
                await viewModel.loadTemplates()
            }
            .task {
                await viewModel.loadTemplates()
            }
            .sheet(item: $selectedTemplate) { template in
                TemplateDetailView(template: template) {
                    Task { await viewModel.loadTemplates() }
                }
            }
            .alert("Error", isPresented: .constant(viewModel.error != nil)) {
                Button("OK") { viewModel.error = nil }
            } message: {
                Text(viewModel.error ?? "")
            }
        }
    }
    
    private var loadingView: some View {
        VStack(spacing: Space.lg) {
            ProgressView()
            Text("Loading templates...")
                .font(TypographyToken.body)
                .foregroundColor(ColorsToken.Text.secondary)
        }
    }
    
    private var emptyStateView: some View {
        VStack(spacing: Space.xl) {
            Image(systemName: "doc.text")
                .font(.system(size: 64))
                .foregroundColor(ColorsToken.Neutral.n400)
            
            VStack(spacing: Space.sm) {
                Text("No Templates Yet")
                    .font(TypographyToken.title2)
                    .foregroundColor(ColorsToken.Text.primary)
                
                Text("Templates are created when you save a workout plan. Ask the coach to create a workout and save it as a template.")
                    .font(TypographyToken.body)
                    .foregroundColor(ColorsToken.Text.secondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, Space.xl)
            }
        }
        .padding(Space.xl)
    }
    
    private var templatesList: some View {
        List {
            ForEach(viewModel.templates) { template in
                TemplateRowView(template: template)
                    .contentShape(Rectangle())
                    .onTapGesture {
                        selectedTemplate = template
                    }
                    .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                        Button(role: .destructive) {
                            Task { await viewModel.deleteTemplate(template) }
                        } label: {
                            Label("Delete", systemImage: "trash")
                        }
                    }
            }
        }
        .listStyle(.insetGrouped)
    }
}

// MARK: - Template Row View

struct TemplateRowView: View {
    let template: WorkoutTemplate
    
    var body: some View {
        VStack(alignment: .leading, spacing: Space.sm) {
            Text(template.name)
                .font(TypographyToken.headline)
                .foregroundColor(ColorsToken.Text.primary)
            
            HStack(spacing: Space.md) {
                Label("\(template.exercises.count) exercises", systemImage: "dumbbell")
                    .font(TypographyToken.caption)
                    .foregroundColor(ColorsToken.Text.secondary)
                
                if let analytics = template.analytics {
                    if let duration = analytics.estimatedDuration {
                        Label("\(duration) min", systemImage: "clock")
                            .font(TypographyToken.caption)
                            .foregroundColor(ColorsToken.Text.secondary)
                    }
                    
                    Label("\(analytics.totalSets) sets", systemImage: "list.number")
                        .font(TypographyToken.caption)
                        .foregroundColor(ColorsToken.Text.secondary)
                }
            }
            
            // Muscle groups
            if let analytics = template.analytics, !analytics.setsPerMuscleGroup.isEmpty {
                let topMuscles = analytics.setsPerMuscleGroup.sorted { $0.value > $1.value }.prefix(3)
                HStack(spacing: Space.xs) {
                    ForEach(Array(topMuscles), id: \.key) { muscle, _ in
                        Text(muscle.capitalized)
                            .font(TypographyToken.caption)
                            .foregroundColor(ColorsToken.Text.primary)
                            .padding(.horizontal, Space.xs)
                            .padding(.vertical, Space.xxs)
                            .background(ColorsToken.Brand.accent100)
                            .cornerRadius(CornerRadiusToken.small)
                    }
                }
            }
        }
        .padding(.vertical, Space.xs)
    }
}

// MARK: - ViewModel

@MainActor
class TemplatesViewModel: ObservableObject {
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
    
    private var userId: String? { authService.currentUser?.uid }
    
    func loadTemplates() async {
        guard let userId = userId else {
            error = "Not logged in"
            return
        }
        
        isLoading = true
        error = nil
        
        do {
            templates = try await templateRepository.getTemplates(userId: userId)
        } catch {
            self.error = error.localizedDescription
        }
        
        isLoading = false
    }
    
    func deleteTemplate(_ template: WorkoutTemplate) async {
        guard let userId = userId else { return }
        
        do {
            try await templateRepository.deleteTemplate(id: template.id, userId: userId)
            await loadTemplates()
        } catch {
            self.error = error.localizedDescription
        }
    }
}

// MARK: - Preview

#Preview {
    TemplatesListView()
}
