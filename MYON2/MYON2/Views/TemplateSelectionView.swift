import SwiftUI

struct TemplateSelectionView: View {
    let onTemplateSelected: (WorkoutTemplate) -> Void
    @Environment(\.presentationMode) var presentationMode
    @StateObject private var viewModel = TemplateSelectionViewModel()
    @State private var searchText = ""
    
    var body: some View {
        NavigationView {
            VStack(spacing: 0) {
                // Search bar
                SearchBar(text: $searchText, placeholder: "Search templates")
                    .padding()
                    .onChange(of: searchText) { newValue in
                        viewModel.searchTemplates(query: newValue)
                    }
                
                // Template list
                Group {
                    if viewModel.isLoading {
                        ProgressView()
                            .frame(maxWidth: .infinity, maxHeight: .infinity)
                    } else if let error = viewModel.error {
                        VStack {
                            Text("Error loading templates")
                                .font(.headline)
                            Text(error.localizedDescription)
                                .font(.subheadline)
                                .foregroundColor(.secondary)
                        }
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                    } else if viewModel.filteredTemplates.isEmpty {
                        VStack {
                            Image(systemName: "doc.text")
                                .font(.system(size: 60))
                                .foregroundColor(.gray)
                            
                            Text("No Templates Found")
                                .font(.title2)
                                .fontWeight(.semibold)
                            
                            Text(searchText.isEmpty ? "You haven't created any templates yet" : "No templates match your search")
                                .font(.subheadline)
                                .foregroundColor(.secondary)
                                .multilineTextAlignment(.center)
                        }
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                    } else {
                        List(viewModel.filteredTemplates) { template in
                            SelectableTemplateRow(template: template) {
                                onTemplateSelected(template)
                            }
                        }
                        .listStyle(PlainListStyle())
                    }
                }
            }
            .navigationTitle("Choose Template")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Cancel") {
                        presentationMode.wrappedValue.dismiss()
                    }
                }
            }
            .task {
                await viewModel.loadTemplates()
            }
        }
    }
}

// MARK: - Selectable Template Row
struct SelectableTemplateRow: View {
    let template: WorkoutTemplate
    let onTap: () -> Void
    
    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                Text(template.name)
                    .font(.headline)
                
                if let description = template.description, !description.isEmpty {
                    Text(description)
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                        .lineLimit(2)
                }
                
                HStack {
                    Text("\(template.exercises.count) exercises")
                        .font(.caption)
                        .foregroundColor(.secondary)
                    
                    let totalSets = template.exercises.flatMap(\.sets).count
                    if totalSets > 0 {
                        Text("• \(totalSets) sets")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }
            }
            .padding(.vertical, 4)
            
            Spacer()
            
            Button(action: onTap) {
                Image(systemName: "arrow.right.circle.fill")
                    .foregroundColor(.blue)
                    .font(.title2)
            }
            .buttonStyle(PlainButtonStyle())
        }
        .contentShape(Rectangle())
        .onTapGesture {
            onTap()
        }
    }
}

// MARK: - Template Selection ViewModel
@MainActor
class TemplateSelectionViewModel: ObservableObject {
    @Published var templates: [WorkoutTemplate] = []
    @Published var filteredTemplates: [WorkoutTemplate] = []
    @Published var isLoading = false
    @Published var error: Error?
    
    private let repository: TemplateRepository
    
    init(repository: TemplateRepository = TemplateRepository()) {
        self.repository = repository
    }
    
    func loadTemplates() async {
        isLoading = true
        error = nil
        
        do {
            guard let userId = AuthService.shared.currentUser?.uid else {
                self.error = NSError(domain: "AuthError", code: -1, userInfo: [NSLocalizedDescriptionKey: "No authenticated user found"])
                isLoading = false
                return
            }
            templates = try await repository.getTemplates(userId: userId)
            filteredTemplates = templates
        } catch {
            self.error = error
        }
        
        isLoading = false
    }
    
    func searchTemplates(query: String) {
        if query.isEmpty {
            filteredTemplates = templates
        } else {
            filteredTemplates = templates.filter { template in
                template.name.lowercased().contains(query.lowercased()) ||
                (template.description?.lowercased().contains(query.lowercased()) ?? false)
            }
        }
    }
}

#Preview {
    TemplateSelectionView { template in
        print("Selected: \(template.name)")
    }
} 