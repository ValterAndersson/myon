import SwiftUI
import Charts

struct CurrentWeekMuscleGroupChart: View {
    let currentWeekStats: WeeklyStats?
    
    // Prepare data for the chart
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
                // Normalize values for stacking
                data.append((group, "Sets", sets * 10)) // Scale up sets for visibility
                data.append((group, "Reps", reps))
                data.append((group, "Load", weight / 100)) // Scale down weight
            }
        }
        
        return data
    }
    
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text("This Week: Muscle Group Breakdown")
                    .font(.headline)
                    .foregroundColor(.secondary)
                
                Text("Showing sets, reps, and load for each muscle group")
                    .font(.caption2)
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
                .chartLegend(position: .bottom, alignment: .center) {
                    HStack(spacing: 16) {
                        Label("Sets (×10)", systemImage: "square.fill")
                            .foregroundColor(.green)
                            .font(.caption)
                        
                        Label("Reps", systemImage: "square.fill")
                            .foregroundColor(.orange)
                            .font(.caption)
                        
                        Label("Load (÷100)", systemImage: "square.fill")
                            .foregroundColor(.blue)
                            .font(.caption)
                    }
                }
            }
        }
        .padding()
        .background(Color(UIColor.secondarySystemBackground))
        .cornerRadius(12)
    }
} 