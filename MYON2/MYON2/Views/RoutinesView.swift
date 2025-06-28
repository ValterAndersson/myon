import SwiftUI

struct RoutinesView: View {
    @State private var searchText = ""
    @State private var showingNewRoutine = false
    @State private var selectedRoutine: Routine?
    @State private var routines: [Routine] = []
    @State private var activeRoutineId: String?
    @State private var showingDeleteAlert = false
    @State private var routineToDelete: Routine?
    @StateObject private var routineRepository = RoutineRepository()
    
    var filteredRoutines: [Routine] {
        if searchText.isEmpty {
            return routines
        } else {
            return routines.filter { routine in
                routine.name.localizedCaseInsensitiveContains(searchText) ||
                routine.description?.localizedCaseInsensitiveContains(searchText) == true
            }
        }
    }
    
    var body: some View {
        VStack(spacing: 0) {
            // Search bar
            SearchBar(text: $searchText, placeholder: "Search routines")
                .padding()
            
            if filteredRoutines.isEmpty {
                // Empty state
                VStack(spacing: 20) {
                    Spacer()
                    
                    Image(systemName: "calendar.badge.plus")
                        .font(.system(size: 60))
                        .foregroundColor(.gray)
                    
                    Text("No Routines Yet")
                        .font(.title2)
                        .fontWeight(.semibold)
                    
                    Text("Create your first routine to organize your weekly training schedule")
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal, 40)
                    
                    Button(action: { showingNewRoutine = true }) {
                        HStack {
                            Image(systemName: "plus")
                            Text("Create Routine")
                        }
                        .padding()
                        .background(Color.blue)
                        .foregroundColor(.white)
                        .cornerRadius(12)
                    }
                    
                    Spacer()
                }
            } else {
                // Routine list
                List {
                                    ForEach(filteredRoutines) { routine in
                    RoutineRow(
                        routine: routine,
                        isActive: activeRoutineId == routine.id,
                        onTap: { selectedRoutine = routine },
                        onSetActive: { setActiveRoutine(routine) },
                        onDelete: { 
                            routineToDelete = routine
                            showingDeleteAlert = true
                        }
                    )
                }
                }
                .listStyle(PlainListStyle())
            }
        }
        .navigationTitle("Workout Routines")
        .navigationBarTitleDisplayMode(.large)
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                Button(action: { showingNewRoutine = true }) {
                    Image(systemName: "plus")
                }
            }
        }
        .sheet(isPresented: $showingNewRoutine) {
            NavigationView {
                RoutineEditorView { routine in
                    routines.append(routine)
                    showingNewRoutine = false
                }
                .toolbar {
                    ToolbarItem(placement: .navigationBarLeading) {
                        Button("Cancel") {
                            showingNewRoutine = false
                        }
                    }
                }
            }
        }
        .sheet(item: $selectedRoutine) { routine in
            NavigationView {
                RoutineDetailView(routine: routine) { updatedRoutine in
                    if let index = routines.firstIndex(where: { $0.id == updatedRoutine.id }) {
                        routines[index] = updatedRoutine
                    }
                    selectedRoutine = nil
                }
                .toolbar {
                    ToolbarItem(placement: .navigationBarTrailing) {
                        Button("Done") {
                            selectedRoutine = nil
                        }
                    }
                }
            }
        }
        .alert("Delete Routine", isPresented: $showingDeleteAlert) {
            Button("Cancel", role: .cancel) {
                routineToDelete = nil
            }
            Button("Delete", role: .destructive) {
                if let routine = routineToDelete {
                    deleteRoutine(routine)
                }
            }
        } message: {
            Text("Are you sure you want to delete '\(routineToDelete?.name ?? "")'? This action cannot be undone.")
        }
        .onAppear {
            loadRoutines()
            loadActiveRoutine()
        }
    }
    
    private func loadRoutines() {
        Task {
            do {
                guard let userId = AuthService.shared.currentUser?.uid else {
                    print("No authenticated user found")
                    routines = []
                    return
                }
                routines = try await routineRepository.getRoutines(userId: userId)
            } catch {
                print("Error loading routines: \(error)")
                routines = [] // Show empty state - no hardcoded data
            }
        }
    }
    
    private func loadActiveRoutine() {
        Task {
            do {
                guard let userId = AuthService.shared.currentUser?.uid else {
                    print("No authenticated user found")
                    return
                }
                if let activeRoutine = try await routineRepository.getActiveRoutine(userId: userId) {
                    await MainActor.run {
                        activeRoutineId = activeRoutine.id
                    }
                }
            } catch {
                print("Error loading active routine: \(error)")
            }
        }
    }
    
    private func setActiveRoutine(_ routine: Routine) {
        Task {
            do {
                try await routineRepository.setActiveRoutine(routineId: routine.id, userId: routine.userId)
                await MainActor.run {
                    activeRoutineId = routine.id
                }
            } catch {
                print("Error setting active routine: \(error)")
            }
        }
    }
    
    private func deleteRoutine(_ routine: Routine) {
        Task {
            do {
                try await routineRepository.deleteRoutine(id: routine.id, userId: routine.userId)
                await MainActor.run {
                    routines.removeAll { $0.id == routine.id }
                    if activeRoutineId == routine.id {
                        activeRoutineId = nil
                    }
                    routineToDelete = nil
                }
            } catch {
                await MainActor.run {
                    print("Error deleting routine: \(error)")
                    routineToDelete = nil
                }
            }
        }
    }
}

struct RoutineRow: View {
    let routine: Routine
    let isActive: Bool
    let onTap: () -> Void
    let onSetActive: () -> Void
    let onDelete: () -> Void
    
    var body: some View {
        Button(action: onTap) {
            VStack(alignment: .leading, spacing: 12) {
                // Header
                HStack {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(routine.name)
                            .font(.headline)
                            .foregroundColor(.primary)
                        
                        Text(routine.description ?? "No description")
                            .font(.subheadline)
                            .foregroundColor(.secondary)
                            .lineLimit(2)
                    }
                    
                    Spacer()
                    
                    VStack(alignment: .trailing, spacing: 4) {
                        // Active indicator
                        if isActive {
                            Text("ACTIVE")
                                .font(.caption2)
                                .fontWeight(.bold)
                                .foregroundColor(.white)
                                .padding(.horizontal, 8)
                                .padding(.vertical, 2)
                                .background(Color.green)
                                .cornerRadius(4)
                        } else {
                            Button("Make Active") {
                                onSetActive()
                            }
                            .font(.caption2)
                            .foregroundColor(.blue)
                        }
                        
                        Text("ROUTINE")
                            .font(.caption2)
                            .fontWeight(.bold)
                            .foregroundColor(.blue)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 2)
                            .background(Color.blue.opacity(0.1))
                            .cornerRadius(4)
                        
                        Text("\(routine.frequency)x/week")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }
                
                // Metrics row
                HStack(spacing: 16) {
                    Label("\(routine.templateIds.count) templates", systemImage: "list.bullet.clipboard")
                        .font(.caption)
                        .foregroundColor(.secondary)
                    
                    Label("\(routine.frequency)x/week", systemImage: "calendar")
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

struct RoutineDetailView: View {
    let routine: Routine
    let onUpdate: (Routine) -> Void
    @State private var showingEditor = false
    
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                // Header
                VStack(alignment: .leading, spacing: 8) {
                    Text(routine.name)
                        .font(.title)
                        .fontWeight(.bold)
                    
                    Text(routine.description ?? "No description")
                        .font(.body)
                        .foregroundColor(.secondary)
                }
                
                // Quick stats
                LazyVGrid(columns: Array(repeating: GridItem(.flexible()), count: 2), spacing: 16) {
                    StatCard(title: "Frequency", value: "\(routine.frequency)x/week")
                    StatCard(title: "Templates", value: "\(routine.templateIds.count)")
                }
                
                // Templates section
                VStack(alignment: .leading, spacing: 12) {
                    Text("Templates")
                        .font(.headline)
                    
                    if routine.templateIds.isEmpty {
                        Text("No templates added yet")
                            .font(.subheadline)
                            .foregroundColor(.secondary)
                    } else {
                        // TODO: Show actual templates
                        ForEach(routine.templateIds, id: \.self) { templateId in
                            Text("Template: \(templateId)")
                                .font(.subheadline)
                                .padding()
                                .background(Color(.systemGray6))
                                .cornerRadius(8)
                        }
                    }
                }
                
                // Additional routine analytics will be added here later
            }
            .padding()
        }
        .navigationTitle("Routine Details")
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
                RoutineEditorView(routine: routine) { updatedRoutine in
                    onUpdate(updatedRoutine)
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
    }
}



#Preview {
    NavigationView {
        RoutinesView()
    }
} 