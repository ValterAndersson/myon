import SwiftUI
import FirebaseFirestore

struct WorkoutHistoryView: View {
    let weekId: String
    @Environment(\.dismiss) private var dismiss
    @State private var workouts: [Workout] = []
    @State private var isLoading = true
    
    private let workoutRepository = WorkoutRepository()
    
    private var weekDateRange: (start: Date, end: Date)? {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        
        guard let startDate = formatter.date(from: weekId) else { return nil }
        
        let calendar = Calendar.current
        guard let endDate = calendar.date(byAdding: .day, value: 6, to: startDate) else { return nil }
        
        return (startDate, endDate)
    }
    
    var body: some View {
        NavigationStack {
            Group {
                if isLoading {
                    ProgressView("Loading workouts...")
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else if workouts.isEmpty {
                    VStack(spacing: 20) {
                        Image(systemName: "calendar.badge.exclamationmark")
                            .font(.system(size: 60))
                            .foregroundColor(.secondary)
                        
                        Text("No workouts found")
                            .font(.title3)
                            .foregroundColor(.primary)
                        
                        Text("No workouts recorded for this week")
                            .font(.subheadline)
                            .foregroundColor(.secondary)
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                    List {
                        ForEach(workouts.sorted(by: { $0.date > $1.date })) { workout in
                            WorkoutRow(workout: workout)
                        }
                    }
                    .listStyle(.insetGrouped)
                }
            }
            .navigationTitle("Week of \(DashboardDataTransformer.formatWeekLabel(weekId))")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Close") { dismiss() }
                }
            }
        }
        .task {
            await loadWorkouts()
        }
    }
    
    private func loadWorkouts() async {
        guard let userId = AuthService.shared.currentUser?.uid,
              let dateRange = weekDateRange else { return }
        
        do {
            let fetchedWorkouts = try await workoutRepository.getWorkouts(
                userId: userId,
                startDate: dateRange.start,
                endDate: dateRange.end
            )
            
            DispatchQueue.main.async {
                self.workouts = fetchedWorkouts
                self.isLoading = false
            }
        } catch {
            print("Error loading workouts: \(error)")
            DispatchQueue.main.async {
                self.isLoading = false
            }
        }
    }
}

struct WorkoutRow: View {
    let workout: Workout
    
    private var formattedDate: String {
        let formatter = DateFormatter()
        formatter.dateStyle = .medium
        formatter.timeStyle = .short
        return formatter.string(from: workout.date)
    }
    
    private var duration: String {
        let totalMinutes = Int(workout.duration / 60)
        let hours = totalMinutes / 60
        let minutes = totalMinutes % 60
        
        if hours > 0 {
            return "\(hours)h \(minutes)m"
        } else {
            return "\(minutes)m"
        }
    }
    
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(workout.name ?? "Workout")
                    .font(.headline)
                    .foregroundColor(.primary)
                
                Spacer()
                
                Text(duration)
                    .font(.subheadline)
                    .foregroundColor(.secondary)
            }
            
            Text(formattedDate)
                .font(.caption)
                .foregroundColor(.secondary)
            
            if !workout.exercises.isEmpty {
                HStack(spacing: 16) {
                    Label("\(workout.exercises.count) exercises", systemImage: "dumbbell")
                        .font(.caption)
                        .foregroundColor(.secondary)
                    
                    if let totalSets = workout.totalSets, totalSets > 0 {
                        Label("\(totalSets) sets", systemImage: "number")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }
            }
        }
        .padding(.vertical, 4)
    }
}

#Preview {
    NavigationView {
        WorkoutHistoryView(weekId: "2024-04-01")
    }
} 