import SwiftUI

struct WorkoutHistoryView: View {
    @StateObject private var viewModel = WorkoutHistoryViewModel()
    @State private var searchText = ""
    @State private var selectedTimeFrame: TimeFrame = .allTime
    
    enum TimeFrame: String, CaseIterable {
        case week = "This Week"
        case month = "This Month"
        case year = "This Year"
        case allTime = "All Time"
    }
    
    var body: some View {
        VStack(spacing: 0) {
            // Search bar
            SearchBar(text: $searchText, placeholder: "Search workouts")
                .padding()
                .onChange(of: searchText) { _ in
                    viewModel.filterWorkouts(searchText: searchText, timeFrame: selectedTimeFrame)
                }
            
            // Time frame picker
            Picker("Time Frame", selection: $selectedTimeFrame) {
                ForEach(TimeFrame.allCases, id: \.self) { timeFrame in
                    Text(timeFrame.rawValue).tag(timeFrame)
                }
            }
            .pickerStyle(SegmentedPickerStyle())
            .padding()
            .onChange(of: selectedTimeFrame) { _ in
                viewModel.filterWorkouts(searchText: searchText, timeFrame: selectedTimeFrame)
            }
            
            // Content
            Group {
                if viewModel.isLoading {
                    LoadingView("Loading workout history...")
                } else if let error = viewModel.error {
                    VStack(spacing: 16) {
                        Image(systemName: "exclamationmark.triangle")
                            .font(.system(size: 50))
                            .foregroundColor(.orange)
                        
                        Text("Error Loading Workouts")
                            .font(.headline)
                        
                        Text(error.localizedDescription)
                            .font(.subheadline)
                            .foregroundColor(.secondary)
                            .multilineTextAlignment(.center)
                        
                        Button("Try Again") {
                            Task {
                                await viewModel.loadWorkouts()
                            }
                        }
                        .padding()
                        .background(Color.blue)
                        .foregroundColor(.white)
                        .cornerRadius(8)
                    }
                    .padding()
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else if viewModel.filteredWorkouts.isEmpty {
                    // Empty state
                    VStack(spacing: 20) {
                        Image(systemName: "list.bullet.clipboard")
                            .font(.system(size: 60))
                            .foregroundColor(.gray)
                        
                        Text(viewModel.workouts.isEmpty ? "No Workouts Yet" : "No Matching Workouts")
                            .font(.title2)
                            .fontWeight(.semibold)
                        
                        Text(viewModel.workouts.isEmpty ? 
                             "Complete your first workout to see it here" :
                             "Try adjusting your search or time frame")
                            .font(.subheadline)
                            .foregroundColor(.secondary)
                            .multilineTextAlignment(.center)
                            .padding(.horizontal, 40)
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                    // Workout list
                    List(viewModel.filteredWorkouts) { workout in
                        NavigationLink(destination: WorkoutHistoryDetailView(workout: workout, templateName: viewModel.getTemplateName(for: workout.sourceTemplateId))) {
                            WorkoutHistoryCard(
                                workout: workout,
                                templateName: viewModel.getTemplateName(for: workout.sourceTemplateId),
                                formatDuration: viewModel.formatDuration,
                                formatDate: viewModel.formatDate,
                                formatTime: viewModel.formatTime,
                                getWorkingSetsCount: viewModel.getWorkingSetsCount
                            )
                        }
                        .listRowSeparator(.hidden)
                        .listRowInsets(EdgeInsets(top: 8, leading: 16, bottom: 8, trailing: 16))
                    }
                    .listStyle(PlainListStyle())
                }
            }
        }
        .navigationTitle("Workout History")
        .task {
            await viewModel.loadWorkouts()
        }
    }
}

struct WorkoutHistoryCard: View {
    let workout: Workout
    let templateName: String?
    let formatDuration: (Date, Date) -> String
    let formatDate: (Date) -> String
    let formatTime: (Date) -> String
    let getWorkingSetsCount: (WorkoutExercise) -> Int
    
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Header with date and time
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text(formatDate(workout.endTime))
                        .font(.headline)
                        .fontWeight(.semibold)
                    
                    HStack(spacing: 16) {
                        HStack(spacing: 4) {
                            Image(systemName: "clock")
                                .font(.caption)
                                .foregroundColor(.secondary)
                            Text("Start: \(formatTime(workout.startTime))")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                        
                        HStack(spacing: 4) {
                            Image(systemName: "clock.fill")
                                .font(.caption)
                                .foregroundColor(.secondary)
                            Text("End: \(formatTime(workout.endTime))")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    }
                }
                
                Spacer()
                
                // Duration badge
                Text(formatDuration(workout.startTime, workout.endTime))
                    .font(.subheadline)
                    .fontWeight(.medium)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 6)
                    .background(Color.blue.opacity(0.1))
                    .foregroundColor(.blue)
                    .cornerRadius(12)
            }
            
            // Template info if available
            if let templateName = templateName {
                HStack(spacing: 6) {
                    Image(systemName: "doc.text")
                        .font(.caption)
                        .foregroundColor(.green)
                    Text("Based on template: ")
                        .font(.caption)
                        .foregroundColor(.secondary)
                    + Text(templateName)
                        .font(.caption)
                        .fontWeight(.medium)
                        .foregroundColor(.green)
                }
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(Color.green.opacity(0.1))
                .cornerRadius(8)
            }
            
            // Exercise summary
            VStack(alignment: .leading, spacing: 4) {
                ForEach(Array(workout.exercises.prefix(4).enumerated()), id: \.element.id) { index, exercise in
                    let workingSets = getWorkingSetsCount(exercise)
                    HStack {
                        Text("\(workingSets)x")
                            .font(.subheadline)
                            .fontWeight(.medium)
                            .foregroundColor(.primary)
                        Text(exercise.name.capitalized)
                            .font(.subheadline)
                            .foregroundColor(.primary)
                        Spacer()
                    }
                }
                
                // Show more indicator if there are more exercises
                if workout.exercises.count > 4 {
                    Text("and \(workout.exercises.count - 4) more exercises...")
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .italic()
                }
            }
            
            // Quick stats
            HStack(spacing: 16) {
                StatPill(title: "Exercises", value: "\(workout.exercises.count)", color: .orange)
                StatPill(title: "Total Sets", value: "\(workout.analytics.totalSets)", color: .purple)
                StatPill(title: "Volume", value: "\(String(format: "%.0f", workout.analytics.totalWeight))\(workout.analytics.weightFormat)", color: .red)
            }
        }
        .padding()
        .background(Color(.systemBackground))
        .cornerRadius(12)
        .shadow(color: .black.opacity(0.1), radius: 4, x: 0, y: 2)
    }
}

struct StatPill: View {
    let title: String
    let value: String
    let color: Color
    
    var body: some View {
        VStack(spacing: 2) {
            Text(value)
                .font(.caption)
                .fontWeight(.bold)
                .foregroundColor(color)
            Text(title)
                .font(.caption2)
                .foregroundColor(.secondary)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background(color.opacity(0.1))
        .cornerRadius(6)
    }
}

#Preview {
    NavigationView {
        WorkoutHistoryView()
    }
} 