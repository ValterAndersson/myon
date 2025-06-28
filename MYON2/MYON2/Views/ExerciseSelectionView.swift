import SwiftUI

struct ExerciseSelectionView: View {
    let onExerciseSelected: (Exercise) -> Void
    @Environment(\.presentationMode) var presentationMode
    @StateObject private var viewModel = ExercisesViewModel()
    @State private var searchText = ""
    @State private var selectedCategory: String?
    @State private var selectedMovementType: String?
    @State private var selectedLevel: String?
    @State private var selectedEquipment: String?
    @State private var selectedPrimaryMuscle: String?
    @State private var selectedSecondaryMuscle: String?
    @State private var isFiltersExpanded = false
    
    var body: some View {
        NavigationView {
            VStack(spacing: 0) {
                // Search bar
                SearchBar(text: $searchText, placeholder: "Search exercises")
                    .padding()
                    .onChange(of: searchText) { newValue in
                        Task {
                            await viewModel.searchExercises(query: newValue)
                        }
                    }
                    .zIndex(1)
                
                // Filters header
                Button(action: { 
                    withAnimation(.easeInOut(duration: 0.2)) { 
                        isFiltersExpanded.toggle() 
                    }
                }) {
                    HStack {
                        Text("Filters")
                            .font(.headline)
                        Spacer()
                        Image(systemName: isFiltersExpanded ? "chevron.up" : "chevron.down")
                            .foregroundColor(.gray)
                            .animation(.easeInOut(duration: 0.2), value: isFiltersExpanded)
                    }
                    .padding(.horizontal)
                    .padding(.vertical, 8)
                }
                .zIndex(1)
                
                // Filters
                if isFiltersExpanded {
                    ScrollView(.vertical, showsIndicators: false) {
                        LazyVStack(spacing: 16) {
                            if !viewModel.categories.isEmpty {
                                FilterChips(title: "Category", options: viewModel.categories, selectedOption: $selectedCategory)
                                    .onChange(of: selectedCategory) { newValue in
                                        Task {
                                            await viewModel.filterByCategory(newValue)
                                        }
                                    }
                            }
                            
                            if !viewModel.movementTypes.isEmpty {
                                FilterChips(title: "Movement Type", options: viewModel.movementTypes, selectedOption: $selectedMovementType)
                                    .onChange(of: selectedMovementType) { newValue in
                                        Task {
                                            await viewModel.filterByMovementType(newValue)
                                        }
                                    }
                            }
                            
                            if !viewModel.levels.isEmpty {
                                FilterChips(title: "Level", options: viewModel.levels, selectedOption: $selectedLevel)
                                    .onChange(of: selectedLevel) { newValue in
                                        Task {
                                            await viewModel.filterByLevel(newValue)
                                        }
                                    }
                            }
                            
                            if !viewModel.equipment.isEmpty {
                                FilterChips(title: "Equipment", options: viewModel.equipment, selectedOption: $selectedEquipment)
                                    .onChange(of: selectedEquipment) { newValue in
                                        Task {
                                            await viewModel.filterByEquipment(newValue)
                                        }
                                    }
                            }
                            
                            if !viewModel.primaryMuscles.isEmpty {
                                FilterChips(title: "Primary Muscles", options: viewModel.primaryMuscles, selectedOption: $selectedPrimaryMuscle)
                                    .onChange(of: selectedPrimaryMuscle) { newValue in
                                        Task {
                                            await viewModel.filterByPrimaryMuscle(newValue)
                                        }
                                    }
                            }
                            
                            if !viewModel.secondaryMuscles.isEmpty {
                                FilterChips(title: "Secondary Muscles", options: viewModel.secondaryMuscles, selectedOption: $selectedSecondaryMuscle)
                                    .onChange(of: selectedSecondaryMuscle) { newValue in
                                        Task {
                                            await viewModel.filterBySecondaryMuscle(newValue)
                                        }
                                    }
                            }
                        }
                        .padding(.horizontal)
                    }
                    .padding(.vertical, 8)
                    .transition(.move(edge: .top).combined(with: .opacity))
                    .zIndex(0)
                }
                
                // Exercise list
                Group {
                    if viewModel.isLoading {
                        ProgressView()
                            .frame(maxWidth: .infinity, maxHeight: .infinity)
                    } else if let error = viewModel.error {
                        VStack {
                            Text("Error loading exercises")
                                .font(.headline)
                            Text(error.localizedDescription)
                                .font(.subheadline)
                                .foregroundColor(.secondary)
                        }
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                    } else if viewModel.exercises.isEmpty {
                        VStack {
                            Text("No exercises found")
                                .font(.headline)
                            Text("Try adjusting your filters or search")
                                .font(.subheadline)
                                .foregroundColor(.secondary)
                        }
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                    } else {
                        List(viewModel.exercises) { exercise in
                            SelectableExerciseRow(exercise: exercise) {
                                onExerciseSelected(exercise)
                            }
                        }
                        .listStyle(PlainListStyle())
                    }
                }
            }
            .navigationTitle("Select Exercise")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Cancel") {
                        presentationMode.wrappedValue.dismiss()
                    }
                }
            }
            .task {
                await viewModel.loadExercises()
            }
        }
    }
}

// MARK: - Selectable Exercise Row
struct SelectableExerciseRow: View {
    let exercise: Exercise
    let onTap: () -> Void
    @State private var showingDetail = false
    
    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                Text(exercise.capitalizedName)
                    .font(.headline)
                
                HStack {
                    Text(exercise.capitalizedCategory)
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                    
                    Text("•")
                        .foregroundColor(.secondary)
                    
                    Text(exercise.capitalizedLevel)
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                }
                
                HStack {
                    Text(exercise.capitalizedMovementType)
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                    
                    Text("•")
                        .foregroundColor(.secondary)
                    
                    Text(exercise.capitalizedEquipment)
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                }
            }
            .padding(.vertical, 4)
            
            Spacer()
            
            // Info button
            Button(action: { showingDetail = true }) {
                Image(systemName: "info.circle")
                    .foregroundColor(.gray)
            }
            .buttonStyle(PlainButtonStyle())
            
            // Add button
            Button(action: onTap) {
                Image(systemName: "plus.circle.fill")
                    .foregroundColor(.green)
                    .font(.title2)
            }
            .buttonStyle(PlainButtonStyle())
        }
        .contentShape(Rectangle())
        .sheet(isPresented: $showingDetail) {
            NavigationView {
                ExerciseDetailModalView(exercise: exercise) {
                    onTap()
                    showingDetail = false
                }
                .toolbar {
                    ToolbarItem(placement: .navigationBarTrailing) {
                        Button("Done") {
                            showingDetail = false
                        }
                    }
                }
            }
        }
    }
}

// MARK: - Exercise Detail Modal
struct ExerciseDetailModalView: View {
    let exercise: Exercise
    let onAdd: () -> Void
    
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                // Header
                VStack(alignment: .leading, spacing: 8) {
                    Text(exercise.capitalizedName)
                        .font(.title)
                        .bold()
                    
                    HStack {
                        Text(exercise.capitalizedCategory)
                            .font(.subheadline)
                            .foregroundColor(.secondary)
                        
                        Text("•")
                            .foregroundColor(.secondary)
                        
                        Text(exercise.capitalizedLevel)
                            .font(.subheadline)
                            .foregroundColor(.secondary)
                    }
                }
                .padding(.horizontal)
                
                // Add button
                Button(action: onAdd) {
                    HStack {
                        Image(systemName: "plus")
                        Text("Add to Workout")
                    }
                    .frame(maxWidth: .infinity)
                    .padding()
                    .background(Color.green)
                    .foregroundColor(.white)
                    .cornerRadius(12)
                }
                .padding(.horizontal)
                
                // Details - Reuse existing structure from ExerciseDetailView
                VStack(spacing: 16) {
                    DetailSection(title: "Level") {
                        Text(exercise.capitalizedLevel)
                    }
                    
                    DetailSection(title: "Movement Type") {
                        Text(exercise.capitalizedMovementType)
                    }
                    
                    DetailSection(title: "Equipment") {
                        Text(exercise.capitalizedEquipment)
                    }
                    
                    DetailSection(title: "Primary Muscles") {
                        TagList(tags: exercise.capitalizedPrimaryMuscles, color: .blue)
                    }
                    
                    DetailSection(title: "Secondary Muscles") {
                        TagList(tags: exercise.capitalizedSecondaryMuscles, color: .green)
                    }
                    
                    DetailSection(title: "Execution") {
                        VStack(alignment: .leading, spacing: 8) {
                            ForEach(exercise.capitalizedExecutionNotes, id: \.self) { note in
                                Text("• \(note)")
                            }
                        }
                    }
                    
                    DetailSection(title: "Common Mistakes") {
                        VStack(alignment: .leading, spacing: 8) {
                            ForEach(exercise.capitalizedCommonMistakes, id: \.self) { mistake in
                                Text("• \(mistake)")
                            }
                        }
                    }
                    
                    DetailSection(title: "Programming") {
                        VStack(alignment: .leading, spacing: 8) {
                            ForEach(exercise.capitalizedProgrammingNotes, id: \.self) { note in
                                Text("• \(note)")
                            }
                        }
                    }
                    
                    DetailSection(title: "Stimulus") {
                        Text(exercise.capitalizedStimulus)
                    }
                    
                    DetailSection(title: "Suitability") {
                        Text(exercise.capitalizedSuitability)
                    }
                }
                .padding(.horizontal)
            }
            .padding(.vertical)
        }
        .navigationTitle("Exercise Details")
        .navigationBarTitleDisplayMode(.inline)
    }
}

#Preview {
    ExerciseSelectionView { exercise in
        print("Selected: \(exercise.name)")
    }
} 