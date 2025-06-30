import SwiftUI
import FirebaseFirestore

struct WorkoutHistoryView: View {
    @State private var searchText = ""
    @State private var selectedTimeFrame: TimeFrame = .allTime
    @State private var workouts: [Workout] = []
    @State private var templates: [WorkoutTemplate] = []
    @State private var isLoading = true
    @State private var selectedWorkout: Workout?
    
    private let workoutRepository = WorkoutRepository()
    private let templateRepository = TemplateRepository()
    
    enum TimeFrame: String, CaseIterable {
        case week = "This Week"
        case month = "This Month"
        case year = "This Year"
        case allTime = "All Time"
    }
    
    var filteredWorkouts: [Workout] {
        var filtered = workouts
        
        // Time filter
        let now = Date()
        switch selectedTimeFrame {
        case .week:
            let weekAgo = Calendar.current.date(byAdding: .weekOfYear, value: -1, to: now) ?? now
            filtered = filtered.filter { $0.endTime >= weekAgo }
        case .month:
            let monthAgo = Calendar.current.date(byAdding: .month, value: -1, to: now) ?? now
            filtered = filtered.filter { $0.endTime >= monthAgo }
        case .year:
            let yearAgo = Calendar.current.date(byAdding: .year, value: -1, to: now) ?? now
            filtered = filtered.filter { $0.endTime >= yearAgo }
        case .allTime:
            break
        }
        
        // Search filter
        if !searchText.isEmpty {
            filtered = filtered.filter { workout in
                // Search in template name
                if let templateName = getTemplateName(for: workout.sourceTemplateId)?.lowercased(),
                   templateName.contains(searchText.lowercased()) {
                    return true
                }
                
                // Search in exercise names
                return workout.exercises.contains { exercise in
                    exercise.name.lowercased().contains(searchText.lowercased())
                }
            }
        }
        
        return filtered.sorted { $0.endTime > $1.endTime }
    }
    
    var body: some View {
        NavigationView {
            VStack(spacing: 0) {
                // Time frame picker
                Picker("Time Frame", selection: $selectedTimeFrame) {
                    ForEach(TimeFrame.allCases, id: \.self) { timeFrame in
                        Text(timeFrame.rawValue).tag(timeFrame)
                    }
                }
                .pickerStyle(SegmentedPickerStyle())
                .padding()
                
                if isLoading {
                    Spacer()
                    ProgressView("Loading workouts...")
                    Spacer()
                } else if filteredWorkouts.isEmpty {
                    Spacer()
                    VStack(spacing: 16) {
                        Image(systemName: "calendar.badge.exclamationmark")
                            .font(.system(size: 60))
                            .foregroundColor(.secondary)
                        
                        Text("No workouts found")
                            .font(.title3)
                            .foregroundColor(.primary)
                        
                        Text(searchText.isEmpty ? "Start your first workout to see history" : "Try adjusting your search or filters")
                            .font(.subheadline)
                            .foregroundColor(.secondary)
                            .multilineTextAlignment(.center)
                    }
                    .padding()
                    Spacer()
                } else {
                    ScrollView {
                        LazyVStack(spacing: 16) {
                            ForEach(filteredWorkouts) { workout in
                                WorkoutHistoryCard(workout: workout, templateName: getTemplateName(for: workout.sourceTemplateId))
                                    .onTapGesture {
                                        selectedWorkout = workout
                                    }
                            }
                        }
                        .padding()
                    }
                }
            }
            .searchable(text: $searchText, prompt: "Search workouts")
            .navigationTitle("Workout History")
            .navigationBarTitleDisplayMode(.large)
            .sheet(item: $selectedWorkout) { workout in
                NavigationView {
                    WorkoutHistoryDetailView(
                        workout: workout,
                        templateName: getTemplateName(for: workout.sourceTemplateId)
                    )
                }
            }
        }
        .task {
            await loadData()
        }
    }
    
    private func loadData() async {
        guard let userId = AuthService.shared.currentUser?.uid else { return }
        
        do {
            // Load workouts and templates in parallel
            async let workoutsTask = workoutRepository.getWorkouts(userId: userId)
            async let templatesTask = templateRepository.getTemplates(userId: userId)
            
            let (fetchedWorkouts, fetchedTemplates) = try await (workoutsTask, templatesTask)
            
            await MainActor.run {
                self.workouts = fetchedWorkouts
                self.templates = fetchedTemplates
                self.isLoading = false
            }
        } catch {
            print("Error loading data: \(error)")
            await MainActor.run {
                self.isLoading = false
            }
        }
    }
    
    private func getTemplateName(for templateId: String?) -> String? {
        guard let templateId = templateId else { return nil }
        return templates.first { $0.id == templateId }?.name
    }
}

struct WorkoutHistoryCard: View {
    let workout: Workout
    let templateName: String?
    
    private var dateFormatter: DateFormatter {
        let formatter = DateFormatter()
        formatter.dateFormat = "d. MMM yyyy"
        return formatter
    }
    
    private var timeFormatter: DateFormatter {
        let formatter = DateFormatter()
        formatter.timeStyle = .short
        return formatter
    }
    
    private var duration: String {
        let totalSeconds = workout.endTime.timeIntervalSince(workout.startTime)
        let hours = Int(totalSeconds) / 3600
        let minutes = (Int(totalSeconds) % 3600) / 60
        
        if hours > 0 {
            return "\(hours)h \(minutes)m"
        } else {
            return "\(minutes)m"
        }
    }
    
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Date and duration header
            HStack {
                Text(dateFormatter.string(from: workout.endTime))
                    .font(.headline)
                
                Spacer()
                
                Text(duration)
                    .font(.subheadline)
                    .foregroundColor(.blue)
            }
            
            // Time info
            HStack(spacing: 16) {
                HStack(spacing: 4) {
                    Image(systemName: "clock")
                        .font(.caption)
                        .foregroundColor(.secondary)
                    Text("Start: \(timeFormatter.string(from: workout.startTime))")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                
                HStack(spacing: 4) {
                    Image(systemName: "clock.fill")
                        .font(.caption)
                        .foregroundColor(.secondary)
                    Text("End: \(timeFormatter.string(from: workout.endTime))")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }
            
            // Template info
            if let templateName = templateName {
                HStack(spacing: 4) {
                    Image(systemName: "doc.text")
                        .font(.caption)
                        .foregroundColor(.green)
                    Text("Based on template: ")
                        .font(.caption)
                        .foregroundColor(.secondary)
                    + Text(templateName)
                        .font(.caption)
                        .foregroundColor(.green)
                        .fontWeight(.medium)
                }
            }
            
            // Exercise list preview
            VStack(alignment: .leading, spacing: 4) {
                ForEach(workout.exercises.prefix(4)) { exercise in
                    HStack {
                        Text("\(getSetCount(for: exercise))x")
                            .font(.caption)
                            .foregroundColor(.secondary)
                        Text(exercise.name)
                            .font(.caption)
                            .foregroundColor(.primary)
                    }
                }
                
                if workout.exercises.count > 4 {
                    Text("and \(workout.exercises.count - 4) more exercises...")
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .italic()
                }
            }
            
            Divider()
            
            // Summary stats
            HStack(spacing: 24) {
                VStack(spacing: 4) {
                    Text("\(workout.exercises.count)")
                        .font(.title2)
                        .fontWeight(.semibold)
                        .foregroundColor(.orange)
                    Text("Exercises")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                
                VStack(spacing: 4) {
                    Text("\(workout.analytics.totalSets)")
                        .font(.title2)
                        .fontWeight(.semibold)
                        .foregroundColor(.purple)
                    Text("Total Sets")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                
                VStack(spacing: 4) {
                    Text("\(Int(workout.analytics.totalWeight))kg")
                        .font(.title2)
                        .fontWeight(.semibold)
                        .foregroundColor(.red)
                    Text("Volume")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                
                Spacer()
                
                Image(systemName: "chevron.right")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
        }
        .padding()
        .background(Color(UIColor.secondarySystemBackground))
        .cornerRadius(12)
    }
    
    private func getSetCount(for exercise: WorkoutExercise) -> Int {
        exercise.sets.filter { isWorkingSet($0.type) }.count
    }
    
    private func isWorkingSet(_ type: String) -> Bool {
        let workingSetTypes = ["Working Set", "Drop Set", "Rest-Pause Set", "Cluster Set", "Tempo Set"]
        return workingSetTypes.contains(type)
    }
} 