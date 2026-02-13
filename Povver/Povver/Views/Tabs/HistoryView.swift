import SwiftUI

/// History Tab - Review what happened
/// Chronological list of completed sessions with infinite scroll
struct HistoryView: View {
    @ObservedObject private var saveService = BackgroundSaveService.shared
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
                                    exerciseCount: workout.exerciseCount,
                                    isSyncing: saveService.isSaving(workout.id)
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

    @Environment(\.dismiss) private var dismiss
    @ObservedObject private var saveService = BackgroundSaveService.shared
    @State private var workout: Workout?
    @State private var isLoading = true
    @State private var showEditSheet = false
    @State private var showDeleteConfirmation = false
    @State private var isDeleting = false

    private var syncState: FocusModeSyncState? {
        saveService.state(for: workoutId)
    }

    var body: some View {
        Group {
            if isLoading {
                loadingView
            } else if let workout = workout {
                WorkoutSummaryContent(workout: workout)
            } else {
                errorView
            }
        }
        .background(Color.bg)
        .navigationTitle("Workout")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                if let state = syncState {
                    if state.isPending {
                        HStack(spacing: 6) {
                            ProgressView()
                                .progressViewStyle(.circular)
                                .scaleEffect(0.7)
                            Text("Syncing")
                                .font(.system(size: 15))
                                .foregroundColor(.textSecondary)
                        }
                    } else if state.isFailed {
                        Button("Retry") {
                            saveService.retry(entityId: workoutId)
                        }
                        .foregroundColor(.warning)
                    }
                } else if workout != nil {
                    Menu {
                        Button("Edit") {
                            showEditSheet = true
                        }
                        Button("Delete Workout", role: .destructive) {
                            showDeleteConfirmation = true
                        }
                    } label: {
                        Image(systemName: "ellipsis.circle")
                            .font(.system(size: 17))
                    }
                } else if !isLoading {
                    // Workout failed to load — still allow deletion
                    Button {
                        showDeleteConfirmation = true
                    } label: {
                        Image(systemName: "trash")
                            .font(.system(size: 15))
                            .foregroundColor(.destructive)
                    }
                }
            }
        }
        .alert("Delete Workout", isPresented: $showDeleteConfirmation) {
            Button("Cancel", role: .cancel) { }
            Button("Delete", role: .destructive) {
                Task { await deleteWorkout() }
            }
        } message: {
            Text("This workout will be permanently deleted. This action cannot be undone.")
        }
        .sheet(isPresented: $showEditSheet) {
            if let workout = workout {
                WorkoutEditView(workout: workout) {
                    // Will auto-reload when background save completes
                }
            }
        }
        .task {
            await loadWorkout()
        }
        .onChange(of: syncState) { oldState, newState in
            // Save completed (entry removed) — reload fresh data
            if oldState != nil && newState == nil {
                Task { await reloadWorkout() }
            }
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

    private func reloadWorkout() async {
        guard let userId = AuthService.shared.currentUser?.uid else { return }
        do {
            workout = try await WorkoutRepository().getWorkout(id: workoutId, userId: userId)
        } catch {
            print("[WorkoutDetailView] Failed to reload workout: \(error)")
        }
    }

    private func deleteWorkout() async {
        guard let userId = AuthService.shared.currentUser?.uid else { return }
        isDeleting = true
        do {
            try await WorkoutRepository().deleteWorkout(userId: userId, id: workoutId)
            dismiss()
        } catch {
            print("[WorkoutDetailView] Failed to delete workout: \(error)")
            isDeleting = false
        }
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
