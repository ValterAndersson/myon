import SwiftUI

struct TemplatesView: View {
    @State private var searchText = ""
    @State private var selectedCategory: String?
    @State private var showingNewTemplate = false
    @State private var selectedTemplate: WorkoutTemplate?
    @State private var templates: [WorkoutTemplate] = []
    @State private var showingDeleteAlert = false
    @State private var templateToDelete: WorkoutTemplate?
    @StateObject private var exercisesViewModel = ExercisesViewModel()
    @StateObject private var templateRepository = TemplateRepository()
    
    // Categories will be provided by AI analysis later
    
    var filteredTemplates: [WorkoutTemplate] {
        var filtered = templates
        
        if !searchText.isEmpty {
            filtered = filtered.filter { template in
                template.name.localizedCaseInsensitiveContains(searchText) ||
                template.description?.localizedCaseInsensitiveContains(searchText) == true
            }
        }
        
        // Remove category filtering for now (AI categories not implemented)
        
        return filtered
    }
    
    var body: some View {
        VStack(spacing: 0) {
            // Search bar
            SearchBar(text: $searchText, placeholder: "Search templates")
                .padding()
            
            // Category filters will be added when AI categorization is implemented
            
            if filteredTemplates.isEmpty {
                // Empty state
                VStack(spacing: 20) {
                    Spacer()
                    
                    Image(systemName: "list.bullet.clipboard")
                        .font(.system(size: 60))
                        .foregroundColor(.gray)
                    
                    Text(templates.isEmpty ? "No Templates Yet" : "No Matching Templates")
                        .font(.title2)
                        .fontWeight(.semibold)
                    
                    Text(templates.isEmpty ? 
                         "Create your first template with muscle targeting and real-time feedback" :
                         "Try adjusting your search or category filter")
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal, 40)
                    
                    if templates.isEmpty {
                        Button(action: { showingNewTemplate = true }) {
                            HStack {
                                Image(systemName: "plus")
                                Text("Create Template")
                            }
                            .padding()
                            .background(Color.blue)
                            .foregroundColor(.white)
                            .cornerRadius(12)
                        }
                    }
                    
                    Spacer()
                }
            } else {
            // Template list
            List {
                    ForEach(filteredTemplates) { template in
                        TemplateRow(
                            template: template, 
                            exercises: exercisesViewModel.exercises,
                            onTap: { selectedTemplate = template },
                            onDelete: { 
                                templateToDelete = template
                                showingDeleteAlert = true
                            }
                        )
                    }
                }
                .listStyle(PlainListStyle())
            }
        }
        .navigationTitle("Workout Templates")
        .navigationBarTitleDisplayMode(.large)
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                Button(action: { showingNewTemplate = true }) {
                    Image(systemName: "plus")
                }
            }
        }
        .sheet(isPresented: $showingNewTemplate) {
            NavigationView {
                TemplateEditorView()
                    .onDisappear {
                        // Check if template was created and saved
                        if let template = TemplateManager.shared.currentTemplate {
                            templates.append(template)
                        }
                        showingNewTemplate = false
                    }
                .toolbar {
                    ToolbarItem(placement: .navigationBarLeading) {
                        Button("Cancel") {
                            showingNewTemplate = false
                        }
                    }
                }
            }
        }
        .sheet(item: $selectedTemplate) { template in
            NavigationView {
                TemplateDetailView(template: template, exercises: exercisesViewModel.exercises) { updatedTemplate in
                    if let index = templates.firstIndex(where: { $0.id == updatedTemplate.id }) {
                        templates[index] = updatedTemplate
                    }
                    selectedTemplate = nil
                }
                .toolbar {
                    ToolbarItem(placement: .navigationBarTrailing) {
                        Button("Done") {
                            selectedTemplate = nil
                        }
                    }
                }
            }
        }
        .alert("Delete Template", isPresented: $showingDeleteAlert) {
            Button("Cancel", role: .cancel) {
                templateToDelete = nil
            }
            Button("Delete", role: .destructive) {
                if let template = templateToDelete {
                    deleteTemplate(template)
                }
            }
        } message: {
            Text("Are you sure you want to delete '\(templateToDelete?.name ?? "")'? This will also remove it from any routines that use this template. This action cannot be undone.")
        }
        .onAppear {
            loadTemplates()
            if exercisesViewModel.exercises.isEmpty {
                Task {
                    await exercisesViewModel.loadExercises()
                }
            }
        }
    }
    
    private func loadTemplates() {
        Task {
            do {
                guard let userId = AuthService.shared.currentUser?.uid else {
                    print("No authenticated user found")
                    templates = []
                    return
                }
                templates = try await templateRepository.getTemplates(userId: userId)
            } catch {
                print("Error loading templates: \(error)")
                templates = [] // Show empty state - no hardcoded data
            }
        }
    }
    
    private func deleteTemplate(_ template: WorkoutTemplate) {
        Task {
            do {
                try await templateRepository.deleteTemplate(id: template.id, userId: template.userId)
                await MainActor.run {
                    templates.removeAll { $0.id == template.id }
                    templateToDelete = nil
                }
            } catch {
                await MainActor.run {
                    print("Error deleting template: \(error)")
                    templateToDelete = nil
                }
            }
        }
    }
}

struct TemplateRow: View {
    let template: WorkoutTemplate
    let exercises: [Exercise]
    let onTap: () -> Void
    let onDelete: () -> Void
    
    var body: some View {
        Button(action: onTap) {
            VStack(alignment: .leading, spacing: 12) {
                // Header
                HStack {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(template.name)
                .font(.headline)
                            .foregroundColor(.primary)
            
                        Text(template.description ?? "No description")
                .font(.subheadline)
                .foregroundColor(.secondary)
                .lineLimit(2)
                    }
                    
                    Spacer()
                    
                    VStack(alignment: .trailing, spacing: 4) {
                        Text("TEMPLATE")
                            .font(.caption2)
                            .fontWeight(.bold)
                            .foregroundColor(.blue)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 2)
                            .background(Color.blue.opacity(0.1))
                            .cornerRadius(4)
                        
                        Text("\(template.exercises.count) exercises")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }
                
                // Quick stimulus preview
                if !exercises.isEmpty {
                    Text("Muscle targeting preview")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                
                // Metrics row
                HStack(spacing: 16) {
                    Label("\(template.exercises.count) exercises", systemImage: "list.bullet")
                        .font(.caption)
                        .foregroundColor(.secondary)
                    
                    Label("Template", systemImage: "doc.text")
                        .font(.caption)
                        .foregroundColor(.secondary)
                    
                    Spacer()
                    
                    // Delete button
                    Button(action: onDelete) {
                        Image(systemName: "trash")
                            .font(.caption)
                            .foregroundColor(.red)
                            .padding(8)
                            .background(Color.red.opacity(0.1))
                            .clipShape(Circle())
                    }
                    .buttonStyle(PlainButtonStyle())
                }
            }
            .padding(.vertical, 8)
        }
        .buttonStyle(PlainButtonStyle())
    }
}

struct TemplateDetailView: View {
    let template: WorkoutTemplate
    let exercises: [Exercise]
    let onUpdate: (WorkoutTemplate) -> Void
    @State private var showingEditor = false
    @State private var showingWorkoutPreview = false
    
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                // Header
                VStack(alignment: .leading, spacing: 8) {
                    HStack {
                        Text(template.name)
                            .font(.title)
                            .fontWeight(.bold)
                        
                        Spacer()
                        
                        Button(action: { showingWorkoutPreview = true }) {
                            HStack {
                                Image(systemName: "play.fill")
                                Text("Start Workout")
                            }
                            .padding(.horizontal, 16)
                            .padding(.vertical, 8)
                            .background(Color.blue)
                            .foregroundColor(.white)
                            .cornerRadius(20)
                        }
                    }
                    
                    Text(template.description ?? "No description")
                        .font(.body)
                        .foregroundColor(.secondary)
                }
                
                // Quick stats
                LazyVGrid(columns: Array(repeating: GridItem(.flexible()), count: 2), spacing: 16) {
                    StatCard(title: "Exercises", value: "\(template.exercises.count)")
                    StatCard(title: "Total Sets", value: "\(template.exercises.flatMap(\.sets).count)")
                }
                
                // Muscle stimulus analysis
                TemplateAnalyticsView(template: template, exercises: exercises)
                
                // Exercises section
                VStack(alignment: .leading, spacing: 12) {
                    Text("Exercises")
                        .font(.headline)
                    
                    ForEach(template.exercises) { exercise in
                        TemplateExerciseDisplayCard(exercise: exercise)
                    }
                }
                

            }
            .padding()
        }
        .navigationTitle("Template Details")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                Button("Edit") {
                    showingEditor = true
                }
            }
        }
        .sheet(isPresented: $showingEditor) {
            NavigationView {
                TemplateEditorView(template: template)
                    .onDisappear {
                        // Check if template was updated and saved
                        if let updatedTemplate = TemplateManager.shared.currentTemplate {
                            onUpdate(updatedTemplate)
                        }
                        showingEditor = false
                    }
                .toolbar {
                    ToolbarItem(placement: .navigationBarLeading) {
                        Button("Cancel") {
                            showingEditor = false
                        }
                    }
                }
            }
        }
        .sheet(isPresented: $showingWorkoutPreview) {
            // TODO: Create workout from template
            NavigationView {
                Text("Start workout from template")
                    .navigationTitle("Start Workout")
                    .toolbar {
                        ToolbarItem(placement: .navigationBarTrailing) {
                            Button("Done") {
                                showingWorkoutPreview = false
                            }
                        }
                    }
            }
        }
    }
}

struct TemplateExerciseDisplayCard: View {
    let exercise: WorkoutTemplateExercise
    @StateObject private var exercisesViewModel = ExercisesViewModel()
    
    private var exerciseName: String {
        if let matchedExercise = exercisesViewModel.exercises.first(where: { $0.id == exercise.exerciseId }) {
            return matchedExercise.name
        }
        return "Unknown Exercise"
    }
    
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Exercise header
            Text(exerciseName.capitalized)
                .font(.headline)
                .textCase(.none)
                .foregroundColor(.primary)
            
            // Sets section
            if exercise.sets.isEmpty {
                Text("No sets configured")
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .padding(.vertical, 8)
            } else {
                VStack(spacing: 8) {
                    ForEach(Array(exercise.sets.enumerated()), id: \.element.id) { index, set in
                        HStack {
                            Text("Set \(index + 1)")
                                .font(.caption)
                                .foregroundColor(.secondary)
                                .frame(width: 50, alignment: .leading)
                            
                            Text("\(String(format: "%.0f", set.weight))kg")
                                .font(.subheadline)
                                .frame(width: 60)
                            
                            Text("\(set.reps) reps")
                                .font(.subheadline)
                                .frame(width: 60)
                            
                            Text("RIR \(set.rir)")
                                .font(.caption)
                                .foregroundColor(.secondary)
                            
                            Spacer()
                        }
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                        .background(Color(.systemGray6))
                    .cornerRadius(8)
                    }
                }
            }
                
            // Rest time
            if let restTime = exercise.restBetweenSets {
                Text("Rest: \(restTime)s between sets")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
        }
        .padding()
        .background(Color(.systemBackground))
        .cornerRadius(12)
        .shadow(radius: 2)
        .onAppear {
            if exercisesViewModel.exercises.isEmpty {
                Task {
                    await exercisesViewModel.loadExercises()
                }
            }
        }
    }
}

struct TemplateAnalyticsView: View {
    let template: WorkoutTemplate
    let exercises: [Exercise]
    @State private var analytics: TemplateAnalytics?
    
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Muscle Targeting")
                .font(.headline)
            
            if let analytics = analytics {
                MuscleStimulusProjection(analytics: analytics)
            } else {
                Text("Calculating muscle stimulus...")
                    .font(.subheadline)
                    .foregroundColor(.secondary)
                    .frame(maxWidth: .infinity, alignment: .center)
                    .padding(.vertical, 20)
            }
        }
        .onAppear {
            calculateAnalytics()
        }
        .onChange(of: template.exercises) {
            calculateAnalytics()
        }
    }
    
    private func calculateAnalytics() {
        analytics = StimulusCalculator.calculateTemplateAnalytics(
            template: template,
            exercises: exercises
        )
    }
}

#Preview {
    NavigationView {
        TemplatesView()
    }
} 