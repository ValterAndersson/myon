import SwiftUI

struct WorkoutHistoryDetailView: View {
    let workout: Workout
    let templateName: String?
    @Environment(\.presentationMode) var presentationMode
    
    var body: some View {
        ScrollView {
            VStack(spacing: 20) {
                // Header
                WorkoutHistoryHeader(workout: workout, templateName: templateName)
                
                // Quick Stats
                WorkoutHistoryQuickStats(workout: workout)
                
                // Detailed Analytics
                WorkoutHistoryAnalyticsSection(workout: workout)
                
                // Exercise Breakdown
                WorkoutHistoryExerciseBreakdown(workout: workout)
            }
            .padding()
        }
        .navigationTitle("Workout Analysis")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                Button("Done") {
                    presentationMode.wrappedValue.dismiss()
                }
            }
        }
    }
}

// MARK: - Workout History Header
struct WorkoutHistoryHeader: View {
    let workout: Workout
    let templateName: String?
    
    var body: some View {
        VStack(spacing: 12) {
            // Analysis icon
            Image(systemName: "chart.bar.fill")
                .font(.system(size: 40))
                .foregroundColor(.blue)
            
            Text("Workout Analysis")
                .font(.title2)
                .fontWeight(.bold)
            
            Text(formatWorkoutDate(workout.endTime))
                .font(.subheadline)
                .foregroundColor(.secondary)
            
            // Template info if available
            if let templateName = templateName {
                HStack(spacing: 6) {
                    Image(systemName: "doc.text")
                        .font(.caption)
                        .foregroundColor(.green)
                    Text("Based on template: ")
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                    + Text(templateName)
                        .font(.subheadline)
                        .fontWeight(.medium)
                        .foregroundColor(.green)
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .background(Color.green.opacity(0.1))
                .cornerRadius(8)
            }
            
            HStack(spacing: 16) {
                VStack(spacing: 4) {
                    Text("Started")
                        .font(.caption)
                        .foregroundColor(.secondary)
                    Text(formatTime(workout.startTime))
                        .font(.subheadline)
                        .fontWeight(.medium)
                }
                
                VStack(spacing: 4) {
                    Text("Finished")
                        .font(.caption)
                        .foregroundColor(.secondary)
                    Text(formatTime(workout.endTime))
                        .font(.subheadline)
                        .fontWeight(.medium)
                }
                
                VStack(spacing: 4) {
                    Text("Duration")
                        .font(.caption)
                        .foregroundColor(.secondary)
                    Text(formatDuration(workout.startTime, workout.endTime))
                        .font(.subheadline)
                        .fontWeight(.medium)
                        .foregroundColor(.blue)
                }
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            .background(Color(.systemGray6))
            .cornerRadius(12)
        }
        .padding()
        .background(Color(.systemGray6))
        .cornerRadius(16)
    }
    
    private func formatWorkoutDate(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.dateStyle = .full
        formatter.timeStyle = .none
        return formatter.string(from: date)
    }
    
    private func formatTime(_ date: Date) -> String {
        let formatter = DateFormatter()
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

// MARK: - Quick Stats (reusing from WorkoutSummaryView but focused on analysis)
struct WorkoutHistoryQuickStats: View {
    let workout: Workout
    @StateObject private var userService = UserService.shared
    
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Performance Summary")
                .font(.headline)
            
            LazyVGrid(columns: [
                GridItem(.flexible()),
                GridItem(.flexible()),
                GridItem(.flexible()),
                GridItem(.flexible())
            ], spacing: 16) {
                StatCard(title: "Exercises", value: "\(workout.exercises.count)")
                StatCard(title: "Working Sets", value: "\(workingSetsCount)")
                StatCard(title: "Completion Rate", value: "\(String(format: "%.0f", completionRate))%")
                StatCard(title: "Total Volume", value: "\(String(format: "%.0f", totalVolume)) \(userService.weightUnit)")
            }
        }
        .padding()
        .background(Color(.systemBackground))
        .cornerRadius(12)
        .shadow(radius: 2)
    }
    
    private var workingSetsCount: Int {
        workout.exercises.reduce(0) { total, exercise in
            total + exercise.sets.filter { isWorkingSet($0.type) }.count
        }
    }
    
    private var completionRate: Double {
        let totalSets = workout.exercises.reduce(0) { $0 + $1.sets.count }
        let completedSets = workout.exercises.reduce(0) { exerciseTotal, exercise in
            exerciseTotal + exercise.sets.reduce(0) { setTotal, set in
                setTotal + (set.isCompleted ? 1 : 0)
            }
        }
        return totalSets > 0 ? (Double(completedSets) / Double(totalSets)) * 100 : 0
    }
    
    private var totalVolume: Double {
        workout.exercises.reduce(0) { exerciseTotal, exercise in
            exerciseTotal + exercise.sets.reduce(0) { setTotal, set in
                // Only count completed working sets in volume calculation
                if set.isCompleted && isWorkingSet(set.type) {
                    return setTotal + (set.weight * Double(set.reps))
                } else {
                    return setTotal
                }
            }
        }
    }
}

// MARK: - Analytics Section (reuse from WorkoutSummaryView)
struct WorkoutHistoryAnalyticsSection: View {
    let workout: Workout
    
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Detailed Analytics")
                .font(.headline)
            
            // Overall workout analytics
            WorkoutOverallAnalytics(analytics: workout.analytics)
            
            // Exercise-specific analytics
            VStack(alignment: .leading, spacing: 12) {
                Text("Exercise Performance")
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

// MARK: - Exercise Breakdown (reuse from WorkoutSummaryView)
struct WorkoutHistoryExerciseBreakdown: View {
    let workout: Workout
    
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Exercise Details")
                .font(.headline)
            
            ForEach(workout.exercises) { exercise in
                WorkoutHistoryExerciseCard(exercise: exercise)
            }
        }
        .padding()
        .background(Color(.systemBackground))
        .cornerRadius(12)
        .shadow(radius: 2)
    }
}

struct WorkoutHistoryExerciseCard: View {
    let exercise: WorkoutExercise
    @StateObject private var userService = UserService.shared
    
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text(exercise.name.capitalized)
                    .font(.headline)
                
                Spacer()
                
                VStack(alignment: .trailing, spacing: 2) {
                    Text("\(workingSets.count) working sets")
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                    if warmUpSets.count > 0 {
                        Text("\(warmUpSets.count) warm-up sets")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }
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
                    WorkoutHistorySetRow(set: set, index: index, userService: userService)
                }
            }
            
            // Working sets performance summary
            if !workingSets.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Working Sets Analysis")
                        .font(.subheadline)
                        .fontWeight(.medium)
                        .foregroundColor(.green)
                    
                    HStack(spacing: 16) {
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Volume: \(String(format: "%.0f", workingVolume)) \(userService.weightUnit)")
                                .font(.caption)
                            Text("Avg Weight: \(String(format: "%.1f", avgWeight)) \(userService.weightUnit)")
                                .font(.caption)
                        }
                        
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Total Reps: \(workingReps)")
                                .font(.caption)
                            Text("Avg Reps: \(String(format: "%.1f", avgReps))")
                                .font(.caption)
                        }
                    }
                    .foregroundColor(.secondary)
                }
                .padding(.horizontal, 8)
                .padding(.vertical, 6)
                .background(Color.green.opacity(0.05))
                .cornerRadius(6)
            }
        }
        .padding()
        .background(Color(.systemGray6))
        .cornerRadius(8)
    }
    
    private var workingSets: [WorkoutExerciseSet] {
        exercise.sets.filter { set in
            set.isCompleted && isWorkingSet(set.type)
        }
    }
    
    private var warmUpSets: [WorkoutExerciseSet] {
        exercise.sets.filter { set in
            set.isCompleted && !isWorkingSet(set.type)
        }
    }
    
    private var workingVolume: Double {
        workingSets.reduce(0) { $0 + ($1.weight * Double($1.reps)) }
    }
    
    private var workingReps: Int {
        workingSets.reduce(0) { $0 + $1.reps }
    }
    
    private var avgWeight: Double {
        guard !workingSets.isEmpty else { return 0 }
        return workingSets.reduce(0) { $0 + $1.weight } / Double(workingSets.count)
    }
    
    private var avgReps: Double {
        guard !workingSets.isEmpty else { return 0 }
        return Double(workingReps) / Double(workingSets.count)
    }
}

// MARK: - Individual Set Row
struct WorkoutHistorySetRow: View {
    let set: WorkoutExerciseSet
    let index: Int
    @ObservedObject var userService: UserService
    
    var body: some View {
        HStack {
            // Set number and completion indicator
            setNumberSection
            
            // Weight
            Text(weightText)
                .font(.subheadline)
                .frame(width: 60, alignment: .center)
                .opacity(set.isCompleted ? 1.0 : 0.6)
            
            // Reps
            Text("\(set.reps)")
                .font(.subheadline)
                .frame(width: 40, alignment: .center)
                .opacity(set.isCompleted ? 1.0 : 0.6)
            
            // RIR
            Text("\(set.rir)")
                .font(.subheadline)
                .frame(width: 30, alignment: .center)
                .opacity(set.isCompleted ? 1.0 : 0.6)
            
            // Set type
            setTypeSection
        }
        .background(backgroundView)
    }
    
    private var setNumberSection: some View {
        HStack(spacing: 4) {
            Text("\(index + 1)")
                .font(.subheadline)
            
            Image(systemName: completionIcon)
                .font(.caption)
                .foregroundColor(completionColor)
        }
        .frame(width: 30, alignment: .leading)
    }
    
    private var weightText: String {
        return "\(String(format: "%.1f", set.weight)) \(userService.weightUnit)"
    }
    
    private var completionIcon: String {
        return set.isCompleted ? "checkmark.circle.fill" : "circle"
    }
    
    private var completionColor: Color {
        return set.isCompleted ? .green : .gray
    }
    
    private var setTypeSection: some View {
        HStack {
            Text(set.type)
                .font(.caption)
                .opacity(set.isCompleted ? 1.0 : 0.6)
            
            if !isWorkingSet(set.type) {
                Text("(not counted)")
                    .font(.caption2)
                    .foregroundColor(.secondary)
                    .italic()
            }
            
            Spacer()
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
    
    private var backgroundView: some View {
        RoundedRectangle(cornerRadius: 4)
            .fill(backgroundColor)
    }
    
    private var backgroundColor: Color {
        if !set.isCompleted {
            return Color.clear
        }
        
        if isWorkingSet(set.type) {
            return Color.green.opacity(0.1)
        } else {
            return Color.blue.opacity(0.05)
        }
    }
}

// Helper function to determine if a set type is a working set
private func isWorkingSet(_ type: String) -> Bool {
    let workingSetTypes = ["Working Set", "Drop Set", "Rest-Pause Set", "Cluster Set", "Tempo Set"]
    return workingSetTypes.contains(type)
}

#Preview {
    NavigationView {
        WorkoutHistoryDetailView(
            workout: Workout(
                id: "sample",
                userId: "user",
                sourceTemplateId: "template",
                createdAt: Date(),
                startTime: Date().addingTimeInterval(-3600),
                endTime: Date(),
                exercises: [],
                notes: nil,
                analytics: WorkoutAnalytics(
                    totalSets: 12,
                    totalReps: 144,
                    totalWeight: 2400,
                    weightFormat: "kg",
                    avgRepsPerSet: 12,
                    avgWeightPerSet: 200,
                    avgWeightPerRep: 16.7,
                    weightPerMuscleGroup: ["chest": 1200, "shoulders": 800],
                    weightPerMuscle: ["pectoralis": 1200, "deltoids": 800],
                    repsPerMuscleGroup: ["chest": 72, "shoulders": 48],
                    repsPerMuscle: ["pectoralis": 72, "deltoids": 48],
                    setsPerMuscleGroup: ["chest": 6, "shoulders": 4],
                    setsPerMuscle: ["pectoralis": 6, "deltoids": 4]
                )
            ),
            templateName: "Push Day A"
        )
    }
} 