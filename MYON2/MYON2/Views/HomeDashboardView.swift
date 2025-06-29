import SwiftUI

struct HomeDashboardView: View {
    @StateObject private var viewModel = WeeklyStatsViewModel()

    var body: some View {
        VStack(spacing: 24) {
            Text("Dashboard")
                .font(.largeTitle).bold()

            if viewModel.isLoading {
                ProgressView("Loading weekly stats...")
            } else if viewModel.hasError {
                VStack(spacing: 12) {
                    Image(systemName: "exclamationmark.triangle")
                        .foregroundColor(.orange)
                        .font(.title2)
                    Text(viewModel.errorMessage ?? "An error occurred")
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                    Button("Retry") {
                        Task {
                            await viewModel.retry()
                        }
                    }
                    .buttonStyle(.borderedProminent)
                }
            } else {
                if let stats = viewModel.stats {
                    VStack(spacing: 12) {
                        StatRow(title: "Workouts", value: "\(stats.workouts)")
                        StatRow(title: "Total Sets", value: "\(stats.totalSets)")
                        StatRow(title: "Total Reps", value: "\(stats.totalReps)")
                        StatRow(title: "Volume", value: String(format: "%.0f kg", stats.totalWeight))
                    }
                }

                if !viewModel.recentStats.isEmpty {
                    WorkoutFrequencyChart(stats: viewModel.recentStats, goal: viewModel.frequencyGoal)
                        .padding(.top)

                    VolumeByMuscleGroupChart(stats: viewModel.recentStats)
                        .padding(.top)

                    VolumeByMuscleChart(stats: viewModel.recentStats)
                        .padding(.top)

                    SetsRepsChart(stats: viewModel.recentStats)
                        .padding(.top)
                } else {
                    Text("No stats available for this week")
                        .foregroundColor(.secondary)
                }
            }
        }
        .padding()
        .task { await viewModel.loadDashboard() }
    }
}
