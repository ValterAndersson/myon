import SwiftUI
import Charts

struct TrainingConsistencyChart: View {
    let stats: [WeeklyStats]
    let goal: Int?
    var onWeekTapped: ((String) -> Void)?
    
    @State private var selectedWeekId: String?
    
    // Limit to last 6-8 weeks
    private var chartData: [WeeklyStats] {
        Array(stats.suffix(8))
    }
    
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Training Consistency")
                .font(.headline)
                .foregroundColor(.secondary)
            
            Chart(chartData) { stat in
                LineMark(
                    x: .value("Week", DashboardDataTransformer.formatWeekLabel(stat.id)),
                    y: .value("Workouts", stat.workouts)
                )
                .foregroundStyle(Color.accentColor)
                .symbol(.circle)
                .symbolSize(100)
                
                PointMark(
                    x: .value("Week", DashboardDataTransformer.formatWeekLabel(stat.id)),
                    y: .value("Workouts", stat.workouts)
                )
                .foregroundStyle(Color.accentColor)
                
                // Goal line
                if let goal = goal {
                    RuleMark(y: .value("Goal", goal))
                        .foregroundStyle(Color.red.opacity(0.5))
                        .lineStyle(StrokeStyle(lineWidth: 2, dash: [5, 5]))
                        .annotation(position: .top, alignment: .leading) {
                            Text("Goal: \(goal)")
                                .font(.caption)
                                .foregroundColor(.red)
                        }
                }
            }
            .frame(height: 200)
            .chartYScale(domain: 0...max(7, chartData.map(\.workouts).max() ?? 0 + 1))
            .chartXAxis {
                AxisMarks(values: .automatic) { _ in
                    AxisValueLabel()
                        .font(.caption)
                    AxisGridLine()
                }
            }
            .chartYAxis {
                AxisMarks(position: .leading)
            }
            .chartOverlay { proxy in
                GeometryReader { geometry in
                    Rectangle()
                        .fill(Color.clear)
                        .contentShape(Rectangle())
                        .onTapGesture { location in
                            guard let plotFrame = proxy.plotAreaFrame else { return }
                            let origin = geometry[plotFrame].origin
                            let tapX = location.x - origin.x
                            
                            // Find closest data point
                            let xScale = plotFrame.width / CGFloat(chartData.count - 1)
                            let index = Int(round(tapX / xScale))
                            
                            if index >= 0 && index < chartData.count {
                                let weekId = chartData[index].id
                                selectedWeekId = weekId
                                onWeekTapped?(weekId)
                            }
                        }
                }
            }
            
            // Legend
            HStack(spacing: 16) {
                Label("Workouts", systemImage: "circle.fill")
                    .font(.caption)
                    .foregroundColor(.accentColor)
                
                if goal != nil {
                    Label("Goal", systemImage: "minus")
                        .font(.caption)
                        .foregroundColor(.red)
                }
            }
            .padding(.top, 4)
        }
        .padding()
        .background(Color(UIColor.secondarySystemBackground))
        .cornerRadius(12)
    }
} 