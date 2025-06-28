import SwiftUI
import Foundation

struct NewWorkoutView: View {
    let onWorkoutStarted: () -> Void
    @Environment(\.presentationMode) var presentationMode
    @StateObject private var workoutManager = ActiveWorkoutManager.shared
    @State private var selectedTemplate: WorkoutTemplate?
    @State private var selectedRoutine: Routine?
    @State private var showingTemplatePicker = false
    @State private var showingRoutinePicker = false
    @State private var showingQuickTemplate = false
    
    var body: some View {
        NavigationView {
            ScrollView(.vertical, showsIndicators: true) {
                VStack(spacing: 20) {
                    // Header
                    VStack(spacing: 8) {
                        Text("Start Your Workout")
                            .font(.title)
                            .fontWeight(.bold)
                        
                        Text("Choose how you want to begin your training session")
                            .font(.subheadline)
                            .foregroundColor(.secondary)
                            .multilineTextAlignment(.center)
                    }
                    .padding(.top)
                    
                    // Quick start options
                    VStack(spacing: 16) {
                        // From Routine
                        Button(action: { showingRoutinePicker = true }) {
                            WorkoutStartOption(
                                icon: "calendar.badge.plus",
                                title: "Start from Routine",
                                description: "Follow your weekly training plan",
                                color: .purple,
                                isRecommended: true
                            )
                        }
                        
                        // From Template
                        Button(action: { showingTemplatePicker = true }) {
                            WorkoutStartOption(
                                icon: "list.bullet.clipboard",
                                title: "Start from Template",
                                description: "Choose from your saved workout templates",
                                color: .orange
                            )
                        }
                        
                        // Quick Template
                        Button(action: { showingQuickTemplate = true }) {
                            WorkoutStartOption(
                                icon: "bolt.circle",
                                title: "Quick Template",
                                description: "Create and start a template with real-time feedback",
                                color: .blue
                            )
                        }
                        
                        // From Scratch
                        Button(action: { startEmptyWorkout() }) {
                            WorkoutStartOption(
                                icon: "plus.circle",
                                title: "Start from Scratch",
                                description: "Build your workout exercise by exercise",
                                color: .green
                            )
                        }
                    }
                    .padding(.horizontal)
                    
                    // Recent workouts section
                    VStack(alignment: .leading, spacing: 12) {
                        HStack {
                            Text("Recent Workouts")
                                .font(.headline)
                            Spacer()
                            Button("View All") {
                                // TODO: Navigate to workout history
                            }
                            .font(.subheadline)
                            .foregroundColor(.blue)
                        }
                        
                        // TODO: Add recent workout cards
                        VStack {
                            Image(systemName: "clock")
                                .font(.title2)
                                .foregroundColor(.gray)
                            Text("No recent workouts")
                                .font(.subheadline)
                                .foregroundColor(.secondary)
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 20)
                        .background(Color(.systemGray6))
                        .cornerRadius(12)
                    }
                    .padding(.horizontal)
                    
                    Spacer(minLength: 20)
                }
            }
            .navigationTitle("New Workout")
            .navigationBarTitleDisplayMode(.inline)
            .navigationBarBackButtonHidden(true)
            .navigationBarItems(leading: 
                Button("Cancel") {
                    presentationMode.wrappedValue.dismiss()
                }
            )
            .sheet(isPresented: $showingTemplatePicker) {
                NavigationView {
                    TemplateSelectionView { template in
                        selectedTemplate = template
                        startWorkoutFromTemplate(template)
                        showingTemplatePicker = false
                    }
                    .navigationBarItems(trailing:
                        Button("Cancel") {
                            showingTemplatePicker = false
                        }
                    )
                }
            }
            .sheet(isPresented: $showingRoutinePicker) {
                NavigationView {
                    RoutineSelectionView { routine in
                        selectedRoutine = routine
                        startWorkoutFromRoutine(routine)
                        showingRoutinePicker = false
                    }
                    .navigationBarItems(trailing:
                        Button("Cancel") {
                            showingRoutinePicker = false
                        }
                    )
                }
            }
            .sheet(isPresented: $showingQuickTemplate) {
                NavigationView {
                    TemplateEditorView()
                        .onDisappear {
                            // Check if template was created and saved
                            if let template = TemplateManager.shared.currentTemplate {
                                startWorkoutFromTemplate(template)
                            }
                            showingQuickTemplate = false
                        }
                    .navigationBarItems(leading:
                        Button("Cancel") {
                            showingQuickTemplate = false
                        }
                    )
                }
            }
        }
    }
    
    private func startEmptyWorkout() {
        workoutManager.startWorkout()
        presentationMode.wrappedValue.dismiss()
        // Delay to ensure dismissal completes before presenting new view
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
            onWorkoutStarted()
        }
    }
    
    private func startWorkoutFromTemplate(_ template: WorkoutTemplate) {
        workoutManager.startWorkout(from: template)
        presentationMode.wrappedValue.dismiss()
        // Delay to ensure dismissal completes before presenting new view
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
            onWorkoutStarted()
        }
    }
    
    private func startWorkoutFromRoutine(_ routine: Routine) {
        // TODO: Implement routine logic - for now, start empty workout
        // In a real implementation, you'd select today's template from the routine
        workoutManager.startWorkout()
        presentationMode.wrappedValue.dismiss()
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
            onWorkoutStarted()
        }
    }
}

struct WorkoutStartOption: View {
    let icon: String
    let title: String
    let description: String
    let color: Color
    var isRecommended: Bool = false
    
    var body: some View {
        HStack(spacing: 16) {
            ZStack {
                Circle()
                    .fill(color.opacity(0.1))
                    .frame(width: 50, height: 50)
                
                Image(systemName: icon)
                    .font(.title2)
                    .foregroundColor(color)
            }
            
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(title)
                        .font(.headline)
                        .foregroundColor(.primary)
                    
                    if isRecommended {
                        Text("RECOMMENDED")
                            .font(.caption2)
                            .fontWeight(.bold)
                            .foregroundColor(.white)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(Color.orange)
                            .cornerRadius(4)
                    }
                }
                
                Text(description)
                    .font(.subheadline)
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.leading)
            }
            
            Spacer()
            
            Image(systemName: "chevron.right")
                .font(.subheadline)
                .foregroundColor(.secondary)
        }
        .padding()
        .background(Color(.systemGray6))
        .cornerRadius(12)
    }
}

// Routine Selection View
struct RoutineSelectionView: View {
    let onSelect: (Routine) -> Void
    @State private var routines: [Routine] = []
    @State private var searchText = ""
    
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
            SearchBar(text: $searchText, placeholder: "Search routines")
                .padding()
            
            if filteredRoutines.isEmpty {
                VStack(spacing: 20) {
                    Spacer()
                    
                    Image(systemName: "calendar.badge.plus")
                        .font(.system(size: 60))
                        .foregroundColor(.gray)
                    
                    Text("No Active Routines")
                        .font(.title2)
                        .fontWeight(.semibold)
                    
                    Text("Create a routine first to start workouts from your weekly plan")
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal, 40)
                    
                    Spacer()
                }
            } else {
                List {
                    ForEach(filteredRoutines) { routine in
                        Button(action: { onSelect(routine) }) {
                            RoutineRow(
                                routine: routine,
                                isActive: false, // For selection view, we don't show active state
                                onTap: { onSelect(routine) },
                                onSetActive: { /* No action needed in selection view */ },
                                onDelete: { /* No action needed in selection view */ }
                            )
                        }
                        .buttonStyle(PlainButtonStyle())
                    }
                }
                .listStyle(PlainListStyle())
            }
        }
        .navigationTitle("Choose Routine")
        .onAppear {
            loadRoutines()
        }
    }
    
    private func loadRoutines() {
        Task {
            do {
                guard let userId = AuthService.shared.currentUser?.uid else {
                    print("No authenticated user found")
                    await MainActor.run {
                        routines = []
                    }
                    return
                }
                let loadedRoutines = try await RoutineRepository().getRoutines(userId: userId)
                await MainActor.run {
                    routines = loadedRoutines
                }
            } catch {
                print("Error loading routines: \(error)")
                await MainActor.run {
                    routines = [] // Empty state
                }
            }
        }
    }
}

#Preview {
    NewWorkoutView {
        print("Workout started")
    }
} 
 
