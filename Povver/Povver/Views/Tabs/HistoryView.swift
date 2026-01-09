import SwiftUI

/// History Tab - Review what happened
/// Chronological list of completed sessions with infinite scroll
struct HistoryView: View {
    @State private var workouts: [HistoryWorkoutItem] = []
    @State private var isLoading = true
    @State private var isLoadingMore = false
    @State private var hasMorePages = true
    @State private var totalWorkoutCount: Int = 0
    
    /// All workouts fetched from repository (full list for pagination)
    @State private var allWorkouts: [Workout] = []
    
    /// Initial page size and load increment
    private let initialPageSize = 25
    private let loadMoreIncrement = 25
    
    var body: some View {
        Group {
            if isLoading {
                loadingView
            } else if workouts.isEmpty {
                emptyStateView
            } else {
                workoutsList
            }
        }
        .background(Color.bg)
        .navigationTitle("")
        .navigationBarTitleDisplayMode(.inline)
        .task {
            await loadInitialWorkouts()
        }
    }
    
    // MARK: - Loading View
    
    private var loadingView: some View {
        VStack(spacing: Space.md) {
            ProgressView()
                .progressViewStyle(.circular)
            Text("Loading history...")
                .font(.system(size: 14))
                .foregroundColor(Color.textSecondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
    
    // MARK: - Empty State
    
    private var emptyStateView: some View {
        VStack(spacing: Space.md) {
            Image(systemName: "clock.arrow.circlepath")
                .font(.system(size: 48))
                .foregroundColor(Color.textTertiary)
            
            Text("No workouts yet")
                .font(.system(size: 17, weight: .semibold))
                .foregroundColor(Color.textPrimary)
            
            Text("Complete your first workout to see it here")
                .font(.system(size: 14))
                .foregroundColor(Color.textSecondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, Space.xl)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
    
    // MARK: - Workouts List
    
    private var workoutsList: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Space.lg) {
                // Header
                VStack(alignment: .leading, spacing: Space.xs) {
                    Text("History")
                        .font(.system(size: 28, weight: .bold))
                        .foregroundColor(Color.textPrimary)
                    
                    Text("\(totalWorkoutCount) completed sessions")
                        .font(.system(size: 15))
                        .foregroundColor(Color.textSecondary)
                }
                .padding(.horizontal, Space.lg)
                .padding(.top, Space.md)
                
                // Grouped by date
                LazyVStack(spacing: Space.md, pinnedViews: [.sectionHeaders]) {
                    ForEach(groupedWorkouts, id: \.date) { group in
                        Section {
                        ForEach(group.workouts) { workout in
                            NavigationLink(destination: WorkoutDetailView(workoutId: workout.id)) {
                                WorkoutRow.history(
                                    name: workout.name,
                                    time: formatTime(workout.date),
                                    duration: formatDuration(workout.duration),
                                    exerciseCount: workout.exerciseCount
                                )
                            }
                            .buttonStyle(PlainButtonStyle())
                        }
                        } header: {
                            DateHeaderView(date: group.date)
                        }
                    }
                    
                    // Load more button
                    if hasMorePages {
                        Button {
                            Task { await loadMoreWorkouts() }
                        } label: {
                            HStack {
                                Spacer()
                                Text("Load More")
                                    .font(.system(size: 14, weight: .medium))
                                    .foregroundColor(Color.accent)
                                Spacer()
                            }
                            .padding(.vertical, Space.md)
                        }
                        .buttonStyle(PlainButtonStyle())
                    }
                }
                .padding(.horizontal, Space.lg)
                
                Spacer(minLength: Space.xxl)
            }
        }
    }
    
    // MARK: - Grouped Workouts
    
    private var groupedWorkouts: [WorkoutGroup] {
        let calendar = Calendar.current
        let grouped = Dictionary(grouping: workouts) { workout in
            calendar.startOfDay(for: workout.date)
        }
        
        return grouped.map { date, workouts in
            WorkoutGroup(date: date, workouts: workouts.sorted { $0.date > $1.date })
        }.sorted { $0.date > $1.date }
    }
    
    // MARK: - Data Loading
    
    private func loadInitialWorkouts() async {
        guard let userId = AuthService.shared.currentUser?.uid else {
            isLoading = false
            return
        }
        
        do {
            let fetchedWorkouts = try await WorkoutRepository().getWorkouts(userId: userId)
            
            // Store all workouts and set total count
            allWorkouts = fetchedWorkouts.sorted { $0.endTime > $1.endTime }
            totalWorkoutCount = allWorkouts.count
            
            // Load initial page
            let initialItems = allWorkouts
                .prefix(initialPageSize)
                .map { workout in
                    HistoryWorkoutItem(
                        id: workout.id,
                        name: workout.displayName,  // Use computed property from Workout model
                        date: workout.endTime,
                        duration: workout.endTime.timeIntervalSince(workout.startTime),
                        exerciseCount: workout.exercises.count,
                        setCount: workout.exercises.flatMap { $0.sets }.count,
                        totalVolume: workout.analytics.totalWeight
                    )
                }
            
            workouts = Array(initialItems)
            hasMorePages = allWorkouts.count > initialPageSize
        } catch {
            print("[HistoryView] Failed to load workouts: \(error)")
        }
        
        isLoading = false
    }
    
    private func loadMoreWorkouts() async {
        guard !isLoadingMore else { return }
        isLoadingMore = true
        
        let currentCount = workouts.count
        let endIndex = min(currentCount + loadMoreIncrement, allWorkouts.count)
        
        let moreItems = allWorkouts[currentCount..<endIndex].map { workout in
            HistoryWorkoutItem(
                id: workout.id,
                name: workout.displayName,
                date: workout.endTime,
                duration: workout.endTime.timeIntervalSince(workout.startTime),
                exerciseCount: workout.exercises.count,
                setCount: workout.exercises.flatMap { $0.sets }.count,
                totalVolume: workout.analytics.totalWeight
            )
        }
        
        workouts.append(contentsOf: moreItems)
        hasMorePages = workouts.count < allWorkouts.count
        isLoadingMore = false
    }
    
    // MARK: - Formatting Helpers
    
    private func formatTime(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.dateFormat = "h:mm a"
        return formatter.string(from: date)
    }
    
    private func formatDuration(_ duration: TimeInterval) -> String {
        let hours = Int(duration) / 3600
        let minutes = (Int(duration) % 3600) / 60
        
        if hours > 0 {
            return "\(hours)h \(minutes)m"
        }
        return "\(minutes)m"
    }
}

// MARK: - History Workout Item

struct HistoryWorkoutItem: Identifiable {
    let id: String
    let name: String
    let date: Date
    let duration: TimeInterval
    let exerciseCount: Int
    let setCount: Int
    let totalVolume: Double
}

// MARK: - Workout Group

private struct WorkoutGroup {
    let date: Date
    let workouts: [HistoryWorkoutItem]
}

// MARK: - Date Header View

private struct DateHeaderView: View {
    let date: Date
    
    private var formattedDate: String {
        let calendar = Calendar.current
        if calendar.isDateInToday(date) {
            return "Today"
        } else if calendar.isDateInYesterday(date) {
            return "Yesterday"
        } else if calendar.isDate(date, equalTo: Date(), toGranularity: .weekOfYear) {
            let formatter = DateFormatter()
            formatter.dateFormat = "EEEE"
            return formatter.string(from: date)
        } else {
            let formatter = DateFormatter()
            formatter.dateFormat = "EEEE, MMM d"
            return formatter.string(from: date)
        }
    }
    
    var body: some View {
        HStack {
            Text(formattedDate)
                .font(.system(size: 14, weight: .semibold))
                .foregroundColor(Color.textSecondary)
            Spacer()
        }
        .padding(.vertical, Space.sm)
        .background(Color.bg)
    }
}

// MARK: - Workout Detail View (Scaffold)

struct WorkoutDetailView: View {
    let workoutId: String
    
    @State private var workout: Workout?
    @State private var isLoading = true
    
    var body: some View {
        Group {
            if isLoading {
                loadingView
            } else if let workout = workout {
                workoutContent(workout)
            } else {
                errorView
            }
        }
        .background(Color.bg)
        .navigationTitle("Workout")
        .navigationBarTitleDisplayMode(.inline)
        .task {
            await loadWorkout()
        }
    }
    
    private var loadingView: some View {
        VStack {
            ProgressView()
                .progressViewStyle(.circular)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
    
    private var errorView: some View {
        VStack(spacing: Space.md) {
            Image(systemName: "exclamationmark.triangle")
                .font(.system(size: 48))
                .foregroundColor(Color.warning)
            
            Text("Workout not found")
                .font(.system(size: 17, weight: .semibold))
                .foregroundColor(Color.textPrimary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
    
    private func workoutContent(_ workout: Workout) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Space.lg) {
                // Header
                workoutHeader(workout)
                
                // Exercises
                if !workout.exercises.isEmpty {
                    ForEach(workout.exercises.indices, id: \.self) { index in
                        exerciseCard(workout.exercises[index], index: index + 1)
                    }
                } else {
                    Text("No exercises recorded")
                        .font(.system(size: 14))
                        .foregroundColor(Color.textSecondary)
                        .padding(.horizontal, Space.lg)
                }
                
                Spacer(minLength: Space.xxl)
            }
        }
    }
    
    private func workoutHeader(_ workout: Workout) -> some View {
        let dateString: String = {
            let fmt = DateFormatter()
            fmt.dateFormat = "EEEE, MMM d 'at' h:mm a"
            return fmt.string(from: workout.endTime)
        }()
        let duration = Int(workout.endTime.timeIntervalSince(workout.startTime) / 60)
        
        return VStack(alignment: .leading, spacing: Space.sm) {
            Text(workout.displayName)
                .font(.system(size: 24, weight: .bold))
                .foregroundColor(Color.textPrimary)
            
            Text(dateString)
                .font(.system(size: 14))
                .foregroundColor(Color.textSecondary)
            
            // Stats row
            HStack(spacing: Space.lg) {
                statItem(
                    value: "\(workout.exercises.count)",
                    label: "exercises"
                )
                statItem(
                    value: "\(workout.exercises.flatMap { $0.sets }.count)",
                    label: "sets"
                )
                statItem(value: "\(duration)", label: "min")
            }
            .padding(.top, Space.sm)
        }
        .padding(.horizontal, Space.lg)
        .padding(.top, Space.md)
    }
    
    private func statItem(value: String, label: String) -> some View {
        VStack(spacing: 2) {
            Text(value)
                .font(.system(size: 20, weight: .bold))
                .foregroundColor(Color.textPrimary)
            Text(label)
                .font(.system(size: 12))
                .foregroundColor(Color.textSecondary)
        }
    }
    
    private func exerciseCard(_ exercise: WorkoutExercise, index: Int) -> some View {
        VStack(alignment: .leading, spacing: Space.sm) {
            // Exercise header
            HStack {
                Text("\(index). \(exercise.name)")
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(Color.textPrimary)
                Spacer()
            }
            
            // Sets - Read-only grid with full details
            if !exercise.sets.isEmpty {
                SetTable(
                    sets: exercise.sets.toSetCellModels(),
                    mode: .readOnly
                )
            }
        }
        .padding(Space.md)
        .background(Color.surface)
        .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.medium))
        .padding(.horizontal, Space.lg)
    }
    
    private func loadWorkout() async {
        guard let userId = AuthService.shared.currentUser?.uid else {
            isLoading = false
            return
        }
        
        do {
            workout = try await WorkoutRepository().getWorkout(id: workoutId, userId: userId)
        } catch {
            print("[WorkoutDetailView] Failed to load workout: \(error)")
        }
        
        isLoading = false
    }
}

#if DEBUG
struct HistoryView_Previews: PreviewProvider {
    static var previews: some View {
        NavigationStack {
            HistoryView()
        }
    }
}
#endif
