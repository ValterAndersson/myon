import SwiftUI
import Charts

struct CurrentWeekMuscleGroupChart: View {
    let currentWeekStats: WeeklyStats?
    @State private var showExpandedBreakdown = false
    
    // Prepare data for grouped bar chart
    private var chartData: [(group: MuscleGroup, metric: String, value: Double)] {
        guard let stats = currentWeekStats else { return [] }
        
        let muscleGroupData = DashboardDataTransformer.transformToMuscleGroupData([stats]).first
        guard let groupData = muscleGroupData else { return [] }
        
        var data: [(MuscleGroup, String, Double)] = []
        
        for group in MuscleGroup.allCases {
            let sets = Double(groupData.groupSets[group] ?? 0)
            let reps = Double(groupData.groupReps[group] ?? 0)
            let weight = groupData.groupVolumes[group] ?? 0
            
            // Only include groups that have data
            if sets > 0 || reps > 0 || weight > 0 {
                data.append((group, "Sets", sets))
                data.append((group, "Reps", reps))
                data.append((group, "Load", weight))
            }
        }
        
        return data
    }
    
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text("This Week: Muscle Group Breakdown")
                    .font(.headline)
                    .foregroundColor(.primary)
                
                Text("Sets, reps, and load by muscle group")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            
            if chartData.isEmpty {
                Text("No workout data for this week")
                    .font(.subheadline)
                    .foregroundColor(.secondary)
                    .frame(height: 200)
                    .frame(maxWidth: .infinity)
                    .background(Color(UIColor.tertiarySystemBackground))
                    .cornerRadius(8)
            } else {
                Chart(chartData, id: \.group) { dataPoint in
                    BarMark(
                        x: .value("Group", dataPoint.group.rawValue),
                        y: .value("Value", dataPoint.value)
                    )
                    .foregroundStyle(by: .value("Metric", dataPoint.metric))
                    .position(by: .value("Metric", dataPoint.metric))
                }
                .frame(height: 250)
                .chartForegroundStyleScale([
                    "Sets": Color.green,
                    "Reps": Color.orange,
                    "Load": Color.blue
                ])
                .chartXAxis {
                    AxisMarks(values: .automatic) { _ in
                        AxisValueLabel()
                            .font(.caption)
                            .foregroundColor(.primary)
                        AxisGridLine()
                    }
                }
                .chartYAxis {
                    AxisMarks(position: .leading) { value in
                        AxisValueLabel()
                            .font(.caption)
                        AxisGridLine()
                    }
                }
                
                // Action button
                Button(action: { showExpandedBreakdown = true }) {
                    Label("Expand Breakdown", systemImage: "arrow.up.left.and.arrow.down.right")
                        .font(.subheadline)
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
                .padding(.top, 8)
            }
        }
        .padding()
        .background(Color(UIColor.secondarySystemBackground))
        .cornerRadius(12)
        .navigationDestination(isPresented: $showExpandedBreakdown) {
            if let weekId = currentWeekStats?.id {
                ExpandedBreakdownView(weekId: weekId)
            }
        }
    }
}

// MARK: - Expanded Breakdown View
struct ExpandedBreakdownView: View {
    let weekId: String
    @Environment(\.dismiss) private var dismiss
    @StateObject private var viewModel = WeeklyStatsViewModel()
    
    private var weekStats: WeeklyStats? {
        viewModel.recentStats.first(where: { $0.id == weekId })
    }
    
    private var muscleGroupData: WeeklyMuscleGroupData? {
        guard let stats = weekStats else { return nil }
        return DashboardDataTransformer.transformToMuscleGroupData([stats]).first
    }
    
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 20) {
                    // Sets per Group
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Sets per Muscle Group")
                            .font(.headline)
                            .foregroundColor(.primary)
                        
                        if let data = muscleGroupData {
                            Chart(MuscleGroup.allCases, id: \.self) { group in
                                let sets = data.groupSets[group] ?? 0
                                if sets > 0 {
                                    BarMark(
                                        x: .value("Group", group.rawValue),
                                        y: .value("Sets", sets)
                                    )
                                    .foregroundStyle(Color.green)
                                    .annotation(position: .top) {
                                        Text("\(sets)")
                                            .font(.caption2)
                                            .foregroundColor(.secondary)
                                    }
                                }
                            }
                            .frame(height: 180)
                        }
                    }
                    .padding()
                    .background(Color(UIColor.secondarySystemBackground))
                    .cornerRadius(12)
                    
                    // Reps per Group
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Reps per Muscle Group")
                            .font(.headline)
                            .foregroundColor(.primary)
                        
                        if let data = muscleGroupData {
                            Chart(MuscleGroup.allCases, id: \.self) { group in
                                let reps = data.groupReps[group] ?? 0
                                if reps > 0 {
                                    BarMark(
                                        x: .value("Group", group.rawValue),
                                        y: .value("Reps", reps)
                                    )
                                    .foregroundStyle(Color.orange)
                                    .annotation(position: .top) {
                                        Text("\(reps)")
                                            .font(.caption2)
                                            .foregroundColor(.secondary)
                                    }
                                }
                            }
                            .frame(height: 180)
                        }
                    }
                    .padding()
                    .background(Color(UIColor.secondarySystemBackground))
                    .cornerRadius(12)
                    
                    // Load per Group
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Load per Muscle Group")
                            .font(.headline)
                            .foregroundColor(.primary)
                        
                        if let data = muscleGroupData {
                            Chart(MuscleGroup.allCases, id: \.self) { group in
                                let load = data.groupVolumes[group] ?? 0
                                if load > 0 {
                                    BarMark(
                                        x: .value("Group", group.rawValue),
                                        y: .value("Load", load)
                                    )
                                    .foregroundStyle(Color.blue)
                                    .annotation(position: .top) {
                                        Text(formatWeight(load))
                                            .font(.caption2)
                                            .foregroundColor(.secondary)
                                    }
                                }
                            }
                            .frame(height: 180)
                            .chartYAxis {
                                AxisMarks(position: .leading) { value in
                                    AxisValueLabel {
                                        if let val = value.as(Double.self) {
                                            Text(formatWeight(val))
                                                .font(.caption)
                                        }
                                    }
                                    AxisGridLine()
                                }
                            }
                        }
                    }
                    .padding()
                    .background(Color(UIColor.secondarySystemBackground))
                    .cornerRadius(12)
                }
                .padding()
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
            await viewModel.loadDashboard(weekCount: 8)
        }
    }
    
    private func formatWeight(_ weight: Double) -> String {
        if weight >= 1000 {
            return String(format: "%.1fk kg", weight / 1000)
        }
        return String(format: "%.0f kg", weight)
    }
} 