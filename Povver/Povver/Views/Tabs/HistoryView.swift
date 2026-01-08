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
        .background(ColorsToken.Background.screen)
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
                .foregroundColor(ColorsToken.Text.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
    
    // MARK: - Empty State
    
    private var emptyStateView: some View {
        VStack(spacing: Space.md) {
            Image(systemName: "clock.arrow.circlepath")
                .font(.system(size: 48))
                .foregroundColor(ColorsToken.Text.muted)
            
            Text("No workouts yet")
                .font(.system(size: 17, weight: .semibold))
                .foregroundColor(ColorsToken.Text.primary)
            
            Text("Complete your first workout to see it here")
                .font(.system(size: 14))
                .foregroundColor(ColorsToken.Text.secondary)
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
                        .foregroundColor(ColorsToken.Text.primary)
                    
                    Text("\(totalWorkoutCount) completed sessions")
                        .font(.system(size: 15))
                        .foregroundColor(ColorsToken.Text.secondary)
                }
                .padding(.horizontal, Space.lg)
                .padding(.top, Space.md)
                
                // Grouped by date
                LazyVStack(spacing: Space.md, pinnedViews: [.sectionHeaders]) {
                    ForEach(groupedWorkouts, id: \.date) { group in
                        Section {
                            ForEach(group.workouts) { workout in
                                NavigationLink(destination: WorkoutDetailView(workoutId: workout.id)) {
                                    HistoryWorkoutRow(workout: workout)
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
                                    .foregroundColor(ColorsToken.Brand.primary)
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
                .foregroundColor(ColorsToken.Text.secondary)
            Spacer()
        }
        .padding(.vertical, Space.sm)
        .background(ColorsToken.Background.screen)
    }
}

// MARK: - History Workout Row

private struct HistoryWorkoutRow: View {
    let workout: HistoryWorkoutItem
    
    private var formattedDuration: String {
        let hours = Int(workout.duration) / 3600
        let minutes = (Int(workout.duration) % 3600) / 60
        
        if hours > 0 {
            return "\(hours)h \(minutes)m"
        }
        return "\(minutes)m"
    }
    
    private var formattedTime: String {
        let formatter = DateFormatter()
        formatter.dateFormat = "h:mm a"
        return formatter.string(from: workout.date)
    }
    
    var body: some View {
        HStack(spacing: Space.md) {
            // Workout info
            VStack(alignment: .leading, spacing: 4) {
                Text(workout.name)
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(ColorsToken.Text.primary)
                
                HStack(spacing: Space.sm) {
                    Text(formattedTime)
                    Text("•")
                    Text(formattedDuration)
                    Text("•")
                    Text("\(workout.exerciseCount) exercises")
                }
                .font(.system(size: 13))
                .foregroundColor(ColorsToken.Text.secondary)
            }
            
            Spacer()
            
            // Stats summary
            VStack(alignment: .trailing, spacing: 2) {
                Text("\(workout.setCount) sets")
                    .font(.system(size: 13, weight: .medium))
                    .foregroundColor(ColorsToken.Text.primary)
                
                if workout.totalVolume > 0 {
                    Text(formatVolume(workout.totalVolume))
                        .font(.system(size: 12))
                        .foregroundColor(ColorsToken.Text.secondary)
                }
            }
            
            Image(systemName: "chevron.right")
                .font(.system(size: 14, weight: .medium))
                .foregroundColor(ColorsToken.Text.muted)
        }
        .padding(Space.md)
        .background(ColorsToken.Surface.card)
        .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.medium))
    }
    
    private func formatVolume(_ volume: Double) -> String {
        if volume >= 1000 {
            return String(format: "%.1fk kg", volume / 1000)
        }
        return String(format: "%.0f kg", volume)
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
        .background(ColorsToken.Background.screen)
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
                .foregroundColor(ColorsToken.State.warning)
            
            Text("Workout not found")
                .font(.system(size: 17, weight: .semibold))
                .foregroundColor(ColorsToken.Text.primary)
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
                        .foregroundColor(ColorsToken.Text.secondary)
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
                .foregroundColor(ColorsToken.Text.primary)
            
            Text(dateString)
                .font(.system(size: 14))
                .foregroundColor(ColorsToken.Text.secondary)
            
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
                .foregroundColor(ColorsToken.Text.primary)
            Text(label)
                .font(.system(size: 12))
                .foregroundColor(ColorsToken.Text.secondary)
        }
    }
    
    private func exerciseCard(_ exercise: WorkoutExercise, index: Int) -> some View {
        VStack(alignment: .leading, spacing: Space.sm) {
            // Exercise header
            HStack {
                Text("\(index). \(exercise.name)")
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(ColorsToken.Text.primary)
                Spacer()
            }
            
            // Sets - Read-only grid with full details
            if !exercise.sets.isEmpty {
                ReadOnlySetGrid(sets: exercise.sets)
            }
        }
        .padding(Space.md)
        .background(ColorsToken.Surface.card)
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

// MARK: - Set Row View

private struct SetRowView: View {
    let set: WorkoutExerciseSet
    let index: Int
    
    var body: some View {
        HStack {
            Text("\(index)")
                .frame(width: 40, alignment: .leading)
            Text(String(format: "%.1f", set.weight))
                .frame(width: 60, alignment: .center)
            Text("\(set.reps)")
                .frame(width: 50, alignment: .center)
            Spacer()
            
            if set.isCompleted {
                Image(systemName: "checkmark.circle.fill")
                    .foregroundColor(ColorsToken.State.success)
                    .font(.system(size: 14))
            }
        }
        .font(.system(size: 14).monospacedDigit())
        .foregroundColor(ColorsToken.Text.primary)
    }
}

// MARK: - Read-Only Set Grid

/// Displays sets in a read-only grid format with SET, WEIGHT, REPS, RIR columns
/// Modeled after FocusModeSetGrid but non-editable
struct ReadOnlySetGrid: View {
    let sets: [WorkoutExerciseSet]
    
    var body: some View {
        VStack(spacing: 0) {
            // Header row
            HStack(spacing: 0) {
                Text("SET")
                    .frame(width: 44, alignment: .center)
                Text("WEIGHT")
                    .frame(maxWidth: .infinity, alignment: .center)
                Text("REPS")
                    .frame(width: 60, alignment: .center)
                Text("RIR")
                    .frame(width: 44, alignment: .center)
                // Checkmark column
                Image(systemName: "checkmark")
                    .frame(width: 36, alignment: .center)
            }
            .font(.system(size: 11, weight: .semibold))
            .foregroundColor(ColorsToken.Text.muted)
            .padding(.vertical, Space.xs)
            .padding(.horizontal, Space.sm)
            
            Divider()
                .background(ColorsToken.Neutral.n100)
            
            // Set rows
            ForEach(sets.indices, id: \.self) { index in
                ReadOnlySetRow(set: sets[index], displayIndex: index + 1)
                
                if index < sets.count - 1 {
                    Divider()
                        .background(ColorsToken.Neutral.n50)
                        .padding(.horizontal, Space.sm)
                }
            }
        }
        .background(ColorsToken.Neutral.n50)
        .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.small))
    }
}

/// A single row in the read-only set grid
private struct ReadOnlySetRow: View {
    let set: WorkoutExerciseSet
    let displayIndex: Int
    
    /// Set type indicator: W=warmup, F=failure, D=drop, number otherwise
    private var setTypeLabel: String {
        let lowercased = set.type.lowercased()
        if lowercased.contains("warm") {
            return "W"
        } else if lowercased.contains("fail") || lowercased.contains("amrap") {
            return "F"
        } else if lowercased.contains("drop") {
            return "D"
        } else {
            return "\(displayIndex)"
        }
    }
    
    /// Color for set type badge
    private var setTypeColor: Color {
        let lowercased = set.type.lowercased()
        if lowercased.contains("warm") {
            return ColorsToken.State.warning // Yellow for warmup sets
        } else if lowercased.contains("fail") || lowercased.contains("amrap") {
            return ColorsToken.State.error // Red for failure sets
        } else if lowercased.contains("drop") {
            return ColorsToken.Brand.primary // Brand color for drop sets
        } else {
            return ColorsToken.Text.secondary
        }
    }
    
    var body: some View {
        HStack(spacing: 0) {
            // SET column with type indicator
            ZStack {
                if setTypeLabel != "\(displayIndex)" {
                    // Special set type badge
                    Text(setTypeLabel)
                        .font(.system(size: 12, weight: .bold))
                        .foregroundColor(.white)
                        .frame(width: 24, height: 24)
                        .background(setTypeColor)
                        .clipShape(RoundedRectangle(cornerRadius: 4))
                } else {
                    // Normal set number
                    Text("\(displayIndex)")
                        .font(.system(size: 14, weight: .medium).monospacedDigit())
                        .foregroundColor(ColorsToken.Text.secondary)
                }
            }
            .frame(width: 44, alignment: .center)
            
            // WEIGHT column
            Text(String(format: "%.1f", set.weight))
                .font(.system(size: 16, weight: .medium).monospacedDigit())
                .foregroundColor(ColorsToken.Text.primary)
                .frame(maxWidth: .infinity, alignment: .center)
            
            // REPS column
            Text("\(set.reps)")
                .font(.system(size: 16, weight: .medium).monospacedDigit())
                .foregroundColor(ColorsToken.Text.primary)
                .frame(width: 60, alignment: .center)
            
            // RIR column
            Text(set.rir > 0 ? "\(set.rir)" : "-")
                .font(.system(size: 14, weight: .medium).monospacedDigit())
                .foregroundColor(set.rir > 0 ? ColorsToken.Text.primary : ColorsToken.Text.muted)
                .frame(width: 44, alignment: .center)
            
            // Checkmark column
            Image(systemName: set.isCompleted ? "checkmark.circle.fill" : "circle")
                .font(.system(size: 16))
                .foregroundColor(set.isCompleted ? ColorsToken.State.success : ColorsToken.Text.muted)
                .frame(width: 36, alignment: .center)
        }
        .padding(.vertical, Space.sm)
        .padding(.horizontal, Space.sm)
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
