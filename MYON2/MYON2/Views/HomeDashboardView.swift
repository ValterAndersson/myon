import SwiftUI

struct HomeDashboardView: View {
    @StateObject private var viewModel = WeeklyStatsViewModel()
    @State private var selectedWeekCount = 8

    var body: some View {
        ScrollView {
            VStack(spacing: 24) {
                // Header
                HStack {
                    Text("Dashboard")
                        .font(.largeTitle).bold()
                    
                    Spacer()
                    
                    // Week selector
                    Picker("Weeks", selection: $selectedWeekCount) {
                        Text("4w").tag(4)
                        Text("8w").tag(8)
                        Text("12w").tag(12)
                    }
                    .pickerStyle(.segmented)
                    .frame(width: 120)
                    .onChange(of: selectedWeekCount) { newValue in
                        Task {
                            await viewModel.loadDashboard(weekCount: newValue)
                        }
                    }
                }

                if viewModel.isLoading {
                    ProgressView("Loading dashboard...")
                        .frame(height: 200)
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
                    .frame(height: 200)
                } else {
                    // Current week stats
                    if let stats = viewModel.stats {
                        VStack(alignment: .leading, spacing: 16) {
                            Text("This Week")
                                .font(.headline)
                                .foregroundColor(.secondary)
                            
                            VStack(spacing: 12) {
                                StatRow(title: "Workouts", value: "\(stats.workouts)")
                                StatRow(title: "Total Sets", value: "\(stats.totalSets)")
                                StatRow(title: "Total Reps", value: "\(stats.totalReps)")
                                StatRow(title: "Volume", value: String(format: "%.0f kg", stats.totalWeight))
                            }
                            .padding()
                            .background(Color(UIColor.secondarySystemBackground))
                            .cornerRadius(12)
                        }
                    }
                    
                    // Charts
                    if !viewModel.recentStats.isEmpty {
                        VStack(alignment: .leading, spacing: 20) {
                            // Workout Frequency Chart
                            VStack(alignment: .leading, spacing: 12) {
                                Text("Workout Frequency")
                                    .font(.headline)
                                    .foregroundColor(.secondary)
                                
                                WorkoutFrequencyChart(
                                    stats: viewModel.recentStats,
                                    goal: viewModel.frequencyGoal
                                )
                                .padding()
                                .background(Color(UIColor.secondarySystemBackground))
                                .cornerRadius(12)
                            }
                            
                            // Volume by Muscle Group
                            VStack(alignment: .leading, spacing: 12) {
                                Text("Volume by Muscle Group")
                                    .font(.headline)
                                    .foregroundColor(.secondary)
                                
                                VolumeByMuscleGroupChart(stats: viewModel.recentStats)
                                    .padding()
                                    .background(Color(UIColor.secondarySystemBackground))
                                    .cornerRadius(12)
                            }
                            
                            // Sets vs Reps
                            VStack(alignment: .leading, spacing: 12) {
                                Text("Sets & Reps Trend")
                                    .font(.headline)
                                    .foregroundColor(.secondary)
                                
                                SetsRepsChart(stats: viewModel.recentStats)
                                    .padding()
                                    .background(Color(UIColor.secondarySystemBackground))
                                    .cornerRadius(12)
                            }
                        }
                        .padding(.top)
                    } else if !viewModel.isLoading {
                        VStack(spacing: 20) {
                            Text("No stats available for this period")
                                .foregroundColor(.secondary)
                                .frame(maxWidth: .infinity)
                            
                            // Debug section
                            #if DEBUG
                            VStack(spacing: 12) {
                                Text("Debug Options")
                                    .font(.headline)
                                
                                Button("Clear Cache & Reload") {
                                    Task {
                                        await viewModel.clearCache()
                                        await viewModel.loadDashboard(weekCount: selectedWeekCount, forceRefresh: true)
                                    }
                                }
                                .buttonStyle(.bordered)
                                
                                Button("Force Refresh") {
                                    Task {
                                        await viewModel.loadDashboard(weekCount: selectedWeekCount, forceRefresh: true)
                                    }
                                }
                                .buttonStyle(.bordered)
                            }
                            .padding()
                            .background(Color.yellow.opacity(0.1))
                            .cornerRadius(8)
                            #endif
                        }
                        .padding(.top, 40)
                    }
                }
            }
            .padding()
        }
        .task { 
            await viewModel.loadDashboard(weekCount: selectedWeekCount)
        }
        .refreshable {
            await viewModel.loadDashboard(weekCount: selectedWeekCount, forceRefresh: true)
        }
    }
}
