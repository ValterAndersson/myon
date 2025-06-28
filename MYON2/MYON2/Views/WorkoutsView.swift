import SwiftUI

struct WorkoutsView: View {
    @State private var showingNewWorkout = false
    @State private var showingActiveWorkout = false
    @State private var showingNewTemplate = false
    @State private var showingNewRoutine = false
    @StateObject private var workoutManager = ActiveWorkoutManager.shared
    @State private var shouldNavigateToDashboard = false
    
    var body: some View {
        NavigationView {
            List {
                // Start Workout Section
                Section(header: Text("Start Workout")) {
                    Button(action: { showingNewWorkout = true }) {
                        MenuRow(
                            title: "New Workout",
                            description: "Start a workout from scratch, template, or routine",
                            icon: "play.circle.fill",
                            color: .red
                        )
                    }
                    .buttonStyle(PlainButtonStyle())
                }
                
                // Templates Section
                Section(header: Text("Templates")) {
                    NavigationLink(destination: TemplatesView()) {
                        MenuRow(
                            title: "Workout Templates",
                            description: "View and manage your workout templates",
                            icon: "list.bullet.clipboard",
                            color: .orange
                        )
                    }
                    
                    Button(action: { showingNewTemplate = true }) {
                        MenuRow(
                            title: "Create Template",
                            description: "Design a new workout template with muscle targeting",
                            icon: "plus.circle.fill",
                            color: .green
                        )
                    }
                    .buttonStyle(PlainButtonStyle())
                }
                
                // Routines Section
                Section(header: Text("Routines")) {
                    NavigationLink(destination: RoutinesView()) {
                        MenuRow(
                            title: "Workout Routines",
                            description: "Manage your weekly training routines",
                            icon: "calendar.badge.plus",
                            color: .purple
                        )
                    }
                    
                    Button(action: { showingNewRoutine = true }) {
                        MenuRow(
                            title: "Create Routine",
                            description: "Build a weekly routine with multiple templates",
                            icon: "plus.square.fill",
                            color: .indigo
                        )
                    }
                    .buttonStyle(PlainButtonStyle())
                }
                
                // Exercises Section
                Section(header: Text("Exercises")) {
                    NavigationLink(destination: ExercisesListView()) {
                        MenuRow(
                            title: "Exercise Library",
                            description: "Browse and search all exercises",
                            icon: "dumbbell.fill",
                            color: .blue
                        )
                    }
                }
                
                // History Section
                Section(header: Text("History")) {
                    NavigationLink(destination: WorkoutHistoryView()) {
                        MenuRow(
                            title: "Workout History",
                            description: "View your past workouts and progress",
                            icon: "clock.fill",
                            color: .gray
                        )
                    }
                }
            }
            .listStyle(InsetGroupedListStyle())
            .navigationTitle("Workouts")
        }
        .sheet(isPresented: $showingNewWorkout) {
            NewWorkoutView {
                showingActiveWorkout = true
            }
        }
        .sheet(isPresented: $showingNewTemplate) {
            NavigationView {
                TemplateEditorView()
                    .onDisappear {
                        // Check if template was created and saved
                        if let template = TemplateManager.shared.currentTemplate {
                            print("Created template: \(template.name)")
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
        .sheet(isPresented: $showingNewRoutine) {
            NavigationView {
                RoutineEditorView { routine in
                    // Handle routine creation
                    print("Created routine: \(routine.name)")
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
        .fullScreenCover(isPresented: $showingActiveWorkout) {
            ActiveWorkoutView(isExpandedFromMinimized: false)
        }
        .onChange(of: showingActiveWorkout) { isShowing in
            if !isShowing {
                // ActiveWorkoutView was dismissed, check if we need to navigate
                handlePostWorkoutNavigation()
            }
        }
        .background(
            NavigationLink(destination: HomeDashboardView(), isActive: $shouldNavigateToDashboard) {
                EmptyView()
            }
            .hidden()
        )
    }
    
    private func handlePostWorkoutNavigation() {
        guard let destination = workoutManager.navigationDestination else { return }
        
        switch destination {
        case .dashboard:
            // Navigate to dashboard after a brief delay
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
                shouldNavigateToDashboard = true
            }
        case .workouts:
            // Already in workouts view, no navigation needed
            break
        case .stayInCurrentView:
            // User navigated away during workout, they're already where they want to be
            break
        }
    }
}

struct MenuRow: View {
    let title: String
    let description: String
    let icon: String
    let color: Color
    
    var body: some View {
        HStack(spacing: 16) {
            Image(systemName: icon)
                .font(.title2)
                .foregroundColor(.white)
                .frame(width: 36, height: 36)
                .background(color)
                .cornerRadius(8)
            
            VStack(alignment: .leading, spacing: 4) {
                Text(title)
                    .font(.headline)
                
                Text(description)
                    .font(.subheadline)
                    .foregroundColor(.secondary)
            }
        }
        .padding(.vertical, 4)
    }
}

struct WorkoutsView_Previews: PreviewProvider {
    static var previews: some View {
        WorkoutsView()
    }
} 