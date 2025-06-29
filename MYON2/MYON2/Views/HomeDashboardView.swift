import SwiftUI

struct HomeDashboardView: View {
    @StateObject private var viewModel = WeeklyStatsViewModel()
    @State private var selectedWeekId: String?
    private let weekCount = 4 // Fixed 4-week window
    
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 16) {
                    // Header
                    HStack {
                        Text("Dashboard")
                            .font(.largeTitle).bold()
                        
                        Spacer()
                    }
                    .padding(.horizontal)
                    
                    if viewModel.isLoading {
                        ProgressView("Loading dashboard...")
                            .frame(maxWidth: .infinity)
                            .frame(height: 200)
                            .background(Color(UIColor.secondarySystemBackground))
                            .cornerRadius(12)
                            .padding(.horizontal)
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
                        .frame(maxWidth: .infinity)
                        .frame(height: 200)
                        .background(Color(UIColor.secondarySystemBackground))
                        .cornerRadius(12)
                        .padding(.horizontal)
                    } else if !viewModel.recentStats.isEmpty || viewModel.stats != nil {
                        VStack(spacing: 16) {
                            // 1. Training Consistency
                            TrainingConsistencyChart(
                                stats: viewModel.recentStats,
                                goal: viewModel.frequencyGoal,
                                onWeekTapped: { weekId in
                                    selectedWeekId = weekId
                                }
                            )
                            .padding(.horizontal)
                            
                            // 2. Weekly Load Progression
                            WeeklyLoadProgressionChart(stats: viewModel.recentStats)
                                .padding(.horizontal)
                            
                            // 3. Muscle Group Volume Trend
                            MuscleGroupVolumeTrendChart(stats: viewModel.recentStats)
                                .padding(.horizontal)
                            
                            // 4. This Week Muscle Group Breakdown
                            CurrentWeekMuscleGroupChart(currentWeekStats: viewModel.stats)
                                .padding(.horizontal)
                            
                            // 5. Top 5 Muscles by Volume
                            TopMusclesChart(stats: viewModel.recentStats)
                                .padding(.horizontal)
                            
                            // 6. Training Balance
                            UndertrainedMusclesView(stats: viewModel.recentStats)
                                .padding(.horizontal)
                            
                            // Debug section
                            #if DEBUG
                            VStack(spacing: 12) {
                                HStack {
                                    Text("Debug: Stats: \(viewModel.stats != nil ? "Yes" : "No")")
                                    Spacer()
                                    Text("Recent: \(viewModel.recentStats.count)")
                                }
                                .font(.caption)
                                .foregroundColor(.orange)
                                
                                HStack(spacing: 12) {
                                                                    Button("Clear Cache") {
                                    Task {
                                        await viewModel.clearCache()
                                        await viewModel.loadDashboard(weekCount: weekCount, forceRefresh: true)
                                    }
                                }
                                .buttonStyle(.bordered)
                                
                                Button("Force Refresh") {
                                    Task {
                                        await viewModel.loadDashboard(weekCount: weekCount, forceRefresh: true)
                                    }
                                }
                                    .buttonStyle(.bordered)
                                }
                            }
                            .padding()
                            .background(Color.yellow.opacity(0.1))
                            .cornerRadius(8)
                            .padding(.horizontal)
                            #endif
                        }
                    } else {
                        VStack(spacing: 20) {
                            Image(systemName: "chart.line.uptrend.xyaxis")
                                .font(.system(size: 60))
                                .foregroundColor(.secondary)
                            
                            Text("No workout data available")
                                .font(.title3)
                                .foregroundColor(.primary)
                            
                            Text("Start tracking your workouts to see insights here")
                                .font(.subheadline)
                                .foregroundColor(.secondary)
                                .multilineTextAlignment(.center)
                        }
                        .frame(maxWidth: .infinity)
                        .frame(height: 300)
                        .background(Color(UIColor.secondarySystemBackground))
                        .cornerRadius(12)
                        .padding(.horizontal)
                    }
                }
                .padding(.vertical)
            }
            .navigationBarHidden(true)
            .background(Color(UIColor.systemBackground))
        }
        .navigationDestination(isPresented: .constant(selectedWeekId != nil)) {
            if let weekId = selectedWeekId {
                WorkoutHistoryView(weekId: weekId)
            }
        }
        .task { 
            await viewModel.loadDashboard(weekCount: weekCount)
        }
        .refreshable {
            await viewModel.loadDashboard(weekCount: weekCount, forceRefresh: true)
        }
    }
}
