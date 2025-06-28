import SwiftUI

struct WorkoutSummaryView: View {
    let workoutId: String
    let onDismiss: (() -> Void)?
    @StateObject private var viewModel = WorkoutSummaryViewModel()
    @Environment(\.presentationMode) var presentationMode
    
    init(workoutId: String, onDismiss: (() -> Void)? = nil) {
        self.workoutId = workoutId
        self.onDismiss = onDismiss
    }
    
    var body: some View {
        NavigationView {
            ScrollView {
                VStack(spacing: 20) {
                    if let workout = viewModel.workout {
                        // Header
                        WorkoutSummaryHeader(workout: workout)
                        
                        // Quick Stats
                        WorkoutQuickStats(workout: workout)
                        
                        // Detailed Analytics
                        WorkoutAnalyticsSection(workout: workout)
                        
                        // Exercise Breakdown
                        WorkoutExerciseBreakdown(workout: workout)
                        
                        // AI Summary Section
                        AISummarySection(isLoading: viewModel.isLoadingAISummary, summary: viewModel.aiSummary)
                        
                        // Sensor Data Section (if applicable)
                        SensorDataSection(isLoading: viewModel.isLoadingSensorData, sensorData: viewModel.sensorData)
                        
                    } else if viewModel.isLoading {
                        ProgressView("Loading workout...")
                            .frame(maxWidth: .infinity, maxHeight: .infinity)
                    } else if let error = viewModel.error {
                        VStack {
                            Text("Error loading workout")
                                .font(.headline)
                            Text(error.localizedDescription)
                                .font(.subheadline)
                                .foregroundColor(.secondary)
                        }
                    }
                }
                .padding()
            }
            .navigationTitle("Workout Complete")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Done") {
                        presentationMode.wrappedValue.dismiss()
                        onDismiss?()
                    }
                }
            }
        }
        .task {
            await viewModel.loadWorkout(id: workoutId)
        }
    }
}

// MARK: - Workout Summary Header
struct WorkoutSummaryHeader: View {
    let workout: Workout
    
    var body: some View {
        VStack(spacing: 12) {
            // Celebration icon
            Image(systemName: "trophy.fill")
                .font(.system(size: 50))
                .foregroundColor(.yellow)
            
            Text("Workout Complete!")
                .font(.title)
                .fontWeight(.bold)
            
            Text(formatWorkoutDate(workout.endTime))
                .font(.subheadline)
                .foregroundColor(.secondary)
            
            Text("Duration: \(formatDuration(workout.startTime, workout.endTime))")
                .font(.headline)
                .padding(.horizontal, 16)
                .padding(.vertical, 8)
                .background(Color.blue.opacity(0.1))
                .cornerRadius(12)
        }
        .padding()
        .background(Color(.systemGray6))
        .cornerRadius(16)
    }
    
    private func formatWorkoutDate(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.dateStyle = .medium
        formatter.timeStyle = .short
        return formatter.string(from: date)
    }
    
    private func formatDuration(_ start: Date, _ end: Date) -> String {
        let duration = end.timeIntervalSince(start)
        let hours = Int(duration) / 3600
        let minutes = (Int(duration) % 3600) / 60
        
        if hours > 0 {
            return "\(hours)h \(minutes)m"
        } else {
            return "\(minutes)m"
        }
    }
}

// MARK: - Quick Stats
struct WorkoutQuickStats: View {
    let workout: Workout
    @StateObject private var userService = UserService.shared
    
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Quick Stats")
                .font(.headline)
            
            LazyVGrid(columns: [
                GridItem(.flexible()),
                GridItem(.flexible()),
                GridItem(.flexible()),
                GridItem(.flexible())
            ], spacing: 16) {
                StatCard(title: "Exercises", value: "\(workout.exercises.count)")
                StatCard(title: "Total Sets", value: "\(totalSets)")
                StatCard(title: "Completed", value: "\(completedSets)/\(totalSets)")
                StatCard(title: "Total Volume", value: "\(String(format: "%.0f", totalVolume)) \(userService.weightUnit)")
            }
        }
        .padding()
        .background(Color(.systemBackground))
        .cornerRadius(12)
        .shadow(radius: 2)
    }
    
    private var totalSets: Int {
        workout.exercises.reduce(0) { $0 + $1.sets.count }
    }
    
    private var completedSets: Int {
        workout.exercises.reduce(0) { exerciseTotal, exercise in
            exerciseTotal + exercise.sets.reduce(0) { setTotal, set in
                setTotal + (set.isCompleted ? 1 : 0)
            }
        }
    }
    
    private var totalVolume: Double {
        workout.exercises.reduce(0) { exerciseTotal, exercise in
            exerciseTotal + exercise.sets.reduce(0) { setTotal, set in
                // Only count completed sets in volume calculation
                if set.isCompleted {
                    return setTotal + (set.weight * Double(set.reps))
                } else {
                    return setTotal
                }
            }
        }
    }
}

struct StatCard: View {
    let title: String
    let value: String
    
    var body: some View {
        VStack(spacing: 4) {
            Text(value)
                .font(.title2)
                .fontWeight(.bold)
                .foregroundColor(.blue)
            
            Text(title)
                .font(.caption)
                .foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding()
        .background(Color(.systemGray6))
        .cornerRadius(8)
    }
}

// MARK: - Workout Analytics Section
struct WorkoutAnalyticsSection: View {
    let workout: Workout
    
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Workout Analytics")
                .font(.headline)
            
            // Overall workout analytics
            WorkoutOverallAnalytics(analytics: workout.analytics)
            
            // Exercise-specific analytics
            VStack(alignment: .leading, spacing: 12) {
                Text("Exercise Analytics")
                    .font(.subheadline)
                    .fontWeight(.semibold)
                
                ForEach(workout.exercises) { exercise in
                    ExerciseAnalyticsCard(exercise: exercise)
                }
            }
            
            // Muscle group breakdown
            if !workout.analytics.weightPerMuscleGroup.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    MuscleGroupBreakdown(
                        weightPerMuscleGroup: workout.analytics.weightPerMuscleGroup, 
                        repsPerMuscleGroup: workout.analytics.repsPerMuscleGroup,
                        setsPerMuscleGroup: workout.analytics.setsPerMuscleGroup,
                        weightFormat: workout.analytics.weightFormat
                    )
                    
                    Text("Note: Exercises can affect multiple muscle groups, therefore calculated volume might be higher than workout total.")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                        .padding(.horizontal)
                }
            }
            
            // Individual muscle breakdown
            if !workout.analytics.weightPerMuscle.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    IndividualMuscleBreakdown(
                        weightPerMuscle: workout.analytics.weightPerMuscle,
                        repsPerMuscle: workout.analytics.repsPerMuscle,
                        setsPerMuscle: workout.analytics.setsPerMuscle,
                        weightFormat: workout.analytics.weightFormat
                    )
                    
                    Text("Muscle breakdown based on common contribution percentages from EMG studies.")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                        .padding(.horizontal)
                }
            }
        }
        .padding()
        .background(Color(.systemBackground))
        .cornerRadius(12)
        .shadow(radius: 2)
    }
}

struct WorkoutOverallAnalytics: View {
    let analytics: WorkoutAnalytics
    
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Overall Stats")
                .font(.subheadline)
                .fontWeight(.semibold)
            
            LazyVGrid(columns: [
                GridItem(.flexible()),
                GridItem(.flexible()),
                GridItem(.flexible())
            ], spacing: 12) {
                AnalyticsCard(title: "Total Sets", value: "\(analytics.totalSets)")
                AnalyticsCard(title: "Total Reps", value: "\(analytics.totalReps)")
                AnalyticsCard(title: "Total Volume", value: "\(String(format: "%.0f", analytics.totalWeight)) \(analytics.weightFormat)")
            }
            
            LazyVGrid(columns: [
                GridItem(.flexible()),
                GridItem(.flexible()),
                GridItem(.flexible())
            ], spacing: 12) {
                AnalyticsCard(title: "Avg Reps/Set", value: String(format: "%.1f", analytics.avgRepsPerSet))
                AnalyticsCard(title: "Avg Weight/Set", value: "\(String(format: "%.1f", analytics.avgWeightPerSet)) \(analytics.weightFormat)")
                AnalyticsCard(title: "Avg Weight/Rep", value: "\(String(format: "%.1f", analytics.avgWeightPerRep)) \(analytics.weightFormat)")
            }
        }
        .padding()
        .background(Color(.systemGray6))
        .cornerRadius(8)
    }
}

struct ExerciseAnalyticsCard: View {
    let exercise: WorkoutExercise
    
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(exercise.name.capitalized)
                .font(.subheadline)
                .fontWeight(.medium)
            
            HStack(spacing: 16) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Sets: \(exercise.analytics.totalSets)")
                        .font(.caption)
                    Text("Reps: \(exercise.analytics.totalReps)")
                        .font(.caption)
                    Text("Volume: \(String(format: "%.0f", exercise.analytics.totalWeight)) \(exercise.analytics.weightFormat)")
                        .font(.caption)
                }
                
                Spacer()
                
                VStack(alignment: .trailing, spacing: 4) {
                    Text("Avg: \(String(format: "%.1f", exercise.analytics.avgRepsPerSet)) reps/set")
                        .font(.caption)
                    Text("Avg: \(String(format: "%.1f", exercise.analytics.avgWeightPerSet)) \(exercise.analytics.weightFormat)/set")
                        .font(.caption)
                    Text("Avg: \(String(format: "%.1f", exercise.analytics.avgWeightPerRep)) \(exercise.analytics.weightFormat)/rep")
                        .font(.caption)
                }
            }
        }
        .padding(12)
        .background(Color(.systemBackground))
        .cornerRadius(8)
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(Color(.systemGray4), lineWidth: 1)
        )
    }
}

struct MuscleGroupBreakdown: View {
    let weightPerMuscleGroup: [String: Double]
    let repsPerMuscleGroup: [String: Double]
    let setsPerMuscleGroup: [String: Int]
    let weightFormat: String
    
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Muscle Group Breakdown")
                .font(.subheadline)
                .fontWeight(.semibold)
            
            // Header row
            HStack {
                Text("Muscle Group")
                    .font(.caption)
                    .fontWeight(.medium)
                    .frame(maxWidth: .infinity, alignment: .leading)
                Text("Sets")
                    .font(.caption)
                    .fontWeight(.medium)
                    .frame(width: 40, alignment: .center)
                Text("Reps")
                    .font(.caption)
                    .fontWeight(.medium)
                    .frame(width: 50, alignment: .center)
                Text("Volume")
                    .font(.caption)
                    .fontWeight(.medium)
                    .frame(width: 80, alignment: .trailing)
            }
            .foregroundColor(.secondary)
            
            ForEach(sortedMuscleGroups, id: \.key) { muscleGroup, weight in
                HStack {
                    Text(muscleGroup.capitalized)
                        .font(.caption)
                        .frame(maxWidth: .infinity, alignment: .leading)
                    
                    Text("\(setsPerMuscleGroup[muscleGroup] ?? 0)")
                        .font(.caption)
                        .frame(width: 40, alignment: .center)
                    
                    Text(String(format: "%.0f", repsPerMuscleGroup[muscleGroup] ?? 0))
                        .font(.caption)
                        .frame(width: 50, alignment: .center)
                    
                    Text("\(String(format: "%.0f", weight)) \(weightFormat)")
                        .font(.caption)
                        .fontWeight(.medium)
                        .frame(width: 80, alignment: .trailing)
                }
                .padding(.vertical, 4)
            }
        }
        .padding()
        .background(Color(.systemGray6))
        .cornerRadius(8)
    }
    
    private var sortedMuscleGroups: [(key: String, value: Double)] {
        weightPerMuscleGroup.sorted { $0.value > $1.value }
    }
}

struct IndividualMuscleBreakdown: View {
    let weightPerMuscle: [String: Double]
    let repsPerMuscle: [String: Double]
    let setsPerMuscle: [String: Int]
    let weightFormat: String
    
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Individual Muscle Breakdown")
                .font(.subheadline)
                .fontWeight(.semibold)
            
            // Header row
            HStack {
                Text("Muscle")
                    .font(.caption)
                    .fontWeight(.medium)
                    .frame(maxWidth: .infinity, alignment: .leading)
                Text("Sets")
                    .font(.caption)
                    .fontWeight(.medium)
                    .frame(width: 40, alignment: .center)
                Text("Reps")
                    .font(.caption)
                    .fontWeight(.medium)
                    .frame(width: 50, alignment: .center)
                Text("Volume")
                    .font(.caption)
                    .fontWeight(.medium)
                    .frame(width: 80, alignment: .trailing)
            }
            .foregroundColor(.secondary)
            
            ForEach(sortedMuscles, id: \.key) { muscle, weight in
                HStack {
                    Text(muscle.capitalized)
                        .font(.caption)
                        .frame(maxWidth: .infinity, alignment: .leading)
                    
                    Text("\(setsPerMuscle[muscle] ?? 0)")
                        .font(.caption)
                        .frame(width: 40, alignment: .center)
                    
                    Text(String(format: "%.0f", repsPerMuscle[muscle] ?? 0))
                        .font(.caption)
                        .frame(width: 50, alignment: .center)
                    
                    Text("\(String(format: "%.0f", weight)) \(weightFormat)")
                        .font(.caption)
                        .fontWeight(.medium)
                        .frame(width: 80, alignment: .trailing)
                }
                .padding(.vertical, 4)
            }
        }
        .padding()
        .background(Color(.systemGray6))
        .cornerRadius(8)
    }
    
    private var sortedMuscles: [(key: String, value: Double)] {
        weightPerMuscle.sorted { $0.value > $1.value }
    }
}

struct AnalyticsCard: View {
    let title: String
    let value: String
    
    var body: some View {
        VStack(spacing: 4) {
            Text(value)
                .font(.headline)
                .fontWeight(.bold)
                .foregroundColor(.blue)
                .minimumScaleFactor(0.8)
            
            Text(title)
                .font(.caption)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .padding(8)
        .background(Color(.systemBackground))
        .cornerRadius(6)
    }
}

// MARK: - Exercise Breakdown
struct WorkoutExerciseBreakdown: View {
    let workout: Workout
    
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Exercise Breakdown")
                .font(.headline)
            
            ForEach(workout.exercises) { exercise in
                ExerciseSummaryCard(exercise: exercise)
            }
        }
        .padding()
        .background(Color(.systemBackground))
        .cornerRadius(12)
        .shadow(radius: 2)
    }
}

struct ExerciseSummaryCard: View {
    let exercise: WorkoutExercise
    @StateObject private var userService = UserService.shared
    
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text(exercise.name.capitalized)
                    .font(.headline)
                
                Spacer()
                
                Text("\(exercise.sets.count) sets")
                    .font(.subheadline)
                    .foregroundColor(.secondary)
            }
            
            // Sets summary
            VStack(spacing: 6) {
                HStack {
                    Text("Set")
                        .font(.caption)
                        .frame(width: 30, alignment: .leading)
                    Text("Weight")
                        .font(.caption)
                        .frame(width: 60, alignment: .center)
                    Text("Reps")
                        .font(.caption)
                        .frame(width: 40, alignment: .center)
                    Text("RIR")
                        .font(.caption)
                        .frame(width: 30, alignment: .center)
                    Text("Type")
                        .font(.caption)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .foregroundColor(.secondary)
                
                ForEach(Array(exercise.sets.enumerated()), id: \.element.id) { index, set in
                    HStack {
                        HStack(spacing: 4) {
                            Text("\(index + 1)")
                                .font(.subheadline)
                            
                            // Completion indicator
                            Image(systemName: set.isCompleted ? "checkmark.circle.fill" : "circle")
                                .font(.caption)
                                .foregroundColor(set.isCompleted ? .green : .gray)
                        }
                        .frame(width: 30, alignment: .leading)
                        
                        Text("\(String(format: "%.1f", set.weight)) \(userService.weightUnit)")
                            .font(.subheadline)
                            .frame(width: 60, alignment: .center)
                            .opacity(set.isCompleted ? 1.0 : 0.6)
                        Text("\(set.reps)")
                            .font(.subheadline)
                            .frame(width: 40, alignment: .center)
                            .opacity(set.isCompleted ? 1.0 : 0.6)
                        Text("\(set.rir)")
                            .font(.subheadline)
                            .frame(width: 30, alignment: .center)
                            .opacity(set.isCompleted ? 1.0 : 0.6)
                        Text(set.type)
                            .font(.caption)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .opacity(set.isCompleted ? 1.0 : 0.6)
                    }
                    .background(
                        RoundedRectangle(cornerRadius: 4)
                            .fill(set.isCompleted ? Color.green.opacity(0.1) : Color.clear)
                    )
                }
            }
        }
        .padding()
        .background(Color(.systemGray6))
        .cornerRadius(8)
    }
}

// MARK: - AI Summary Section
struct AISummarySection: View {
    let isLoading: Bool
    let summary: String?
    
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("AI Workout Analysis")
                .font(.headline)
            
            if isLoading {
                HStack {
                    ProgressView()
                        .scaleEffect(0.8)
                    Text("Analyzing your workout...")
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding()
                .background(Color(.systemGray6))
                .cornerRadius(8)
            } else if let summary = summary {
                Text(summary)
                    .font(.subheadline)
                    .padding()
                    .background(Color(.systemGray6))
                    .cornerRadius(8)
            } else {
                VStack(alignment: .leading, spacing: 8) {
                    Text("AI analysis will be available shortly")
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                    Text("Check back in a few minutes for personalized insights about your workout performance.")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                .padding()
                .background(Color(.systemGray6))
                .cornerRadius(8)
            }
        }
        .padding()
        .background(Color(.systemBackground))
        .cornerRadius(12)
        .shadow(radius: 2)
    }
}

// MARK: - Sensor Data Section
struct SensorDataSection: View {
    let isLoading: Bool
    let sensorData: String?
    
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Sensor Data Analysis")
                .font(.headline)
            
            if isLoading {
                HStack {
                    ProgressView()
                        .scaleEffect(0.8)
                    Text("Processing sensor data...")
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding()
                .background(Color(.systemGray6))
                .cornerRadius(8)
            } else if let sensorData = sensorData {
                Text(sensorData)
                    .font(.subheadline)
                    .padding()
                    .background(Color(.systemGray6))
                    .cornerRadius(8)
            } else {
                VStack(alignment: .leading, spacing: 8) {
                    Text("No sensor data available")
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                    Text("Connect sensors during your next workout to get detailed movement analysis and performance insights.")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                .padding()
                .background(Color(.systemGray6))
                .cornerRadius(8)
            }
        }
        .padding()
        .background(Color(.systemBackground))
        .cornerRadius(12)
        .shadow(radius: 2)
    }
}

// MARK: - ViewModel
@MainActor
class WorkoutSummaryViewModel: ObservableObject {
    @Published var workout: Workout?
    @Published var isLoading = false
    @Published var error: Error?
    
    // AI Summary
    @Published var isLoadingAISummary = false
    @Published var aiSummary: String?
    
    // Sensor Data
    @Published var isLoadingSensorData = false
    @Published var sensorData: String?
    
    private let workoutRepository = WorkoutRepository()
    
    func loadWorkout(id: String) async {
        isLoading = true
        error = nil
        
        do {
            // Get current user ID from AuthService
            guard let userId = AuthService.shared.currentUser?.uid else {
                self.error = WorkoutError.noUserID
                isLoading = false
                return
            }
            
            workout = try await workoutRepository.getWorkout(id: id, userId: userId)
            
            // Start loading AI summary and sensor data in background
            await loadAISummary(workoutId: id)
            await loadSensorData(workoutId: id)
        } catch {
            self.error = error
        }
        
        isLoading = false
    }
    
    private func loadAISummary(workoutId: String) async {
        isLoadingAISummary = true
        
        // Simulate AI summary loading
        try? await Task.sleep(nanoseconds: 2_000_000_000) // 2 seconds
        
        // TODO: Replace with actual AI summary service call
        aiSummary = "Great workout! You maintained consistent intensity across all exercises. Your progressive overload on the compound movements shows good strength development. Consider adding more volume to your accessory work next session."
        
        isLoadingAISummary = false
    }
    
    private func loadSensorData(workoutId: String) async {
        isLoadingSensorData = true
        
        // Simulate sensor data processing
        try? await Task.sleep(nanoseconds: 3_000_000_000) // 3 seconds
        
        // TODO: Replace with actual sensor data processing
        // For now, just show placeholder since no sensors are connected
        sensorData = nil
        
        isLoadingSensorData = false
    }
}

#Preview {
    WorkoutSummaryView(workoutId: "sample_workout_id")
} 