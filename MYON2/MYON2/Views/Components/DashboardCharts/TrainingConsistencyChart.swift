import SwiftUI
import Charts

struct TrainingConsistencyChart: View {
    let stats: [WeeklyStats]
    let goal: Int?
    
    // Limit to last 4 weeks (oldest to newest)
    private var chartData: [WeeklyStats] {
        Array(stats.suffix(4).reversed())
    }
    
    private var yAxisDomain: ClosedRange<Int> {
        let maxWorkouts = chartData.map(\.workouts).max() ?? 0
        let goalValue = goal ?? 3
        return 0...max(5, max(maxWorkouts, goalValue) + 1)
    }
    
    @ViewBuilder
    private var chartContent: some View {
        Chart {
            ForEach(chartData, id: \.id) { stat in
                // Create stacked segments for each workout
                ForEach(0..<stat.workouts, id: \.self) { index in
                    BarMark(
                        x: .value("Week", DashboardDataTransformer.formatWeekLabel(stat.id)),
                        y: .value("Start", index),
                        height: 1
                    )
                    .foregroundStyle(Color.accentColor.opacity(0.9))
                    .cornerRadius(2)
                }
                
                // Invisible bar for tap target
                BarMark(
                    x: .value("Week", DashboardDataTransformer.formatWeekLabel(stat.id)),
                    y: .value("Total", stat.workouts)
                )
                .foregroundStyle(.clear)
                .annotation(position: .top) {
                    if stat.workouts > 0 {
                        Text("\(stat.workouts)")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                    }
                }
            }
            
            // Goal line
            if let goal = goal {
                RuleMark(y: .value("Goal", goal))
                    .foregroundStyle(Color.red.opacity(0.5))
                    .lineStyle(StrokeStyle(lineWidth: 2, dash: [5, 5]))
                    .annotation(position: .top, alignment: .trailing) {
                        Text("Goal: \(goal)")
                            .font(.caption)
                            .foregroundColor(.red)
                            .padding(.trailing, 4)
                    }
            }
        }
    }
    
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            VStack(alignment: .leading, spacing: 4) {
                Text("Training Consistency")
                    .font(.headline)
                    .foregroundColor(.primary)
                
                Text("Workouts per week (last 4 weeks)")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            
            chartContent
                .frame(height: 200)
                .chartYScale(domain: yAxisDomain)
                .chartXAxis {
                    AxisMarks(values: .automatic) { _ in
                        AxisValueLabel()
                            .font(.caption)
                        AxisGridLine()
                    }
                }
                .chartYAxis {
                    AxisMarks(position: .trailing) { value in
                        AxisValueLabel()
                                            AxisGridLine()
                }
            }
        }
        .padding()
        .background(Color(UIColor.secondarySystemBackground))
        .cornerRadius(12)
    }
} 