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
    
    private var yAxisDomain: ClosedRange<Int> {
        let maxWorkouts = chartData.map(\.workouts).max() ?? 0
        return 0...max(7, maxWorkouts + 1)
    }
    
    @ViewBuilder
    private var chartContent: some View {
        Chart {
            ForEach(chartData, id: \.id) { stat in
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
            }
            
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
    }
    
    @ViewBuilder
    private var legend: some View {
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
    
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Training Consistency")
                .font(.headline)
                .foregroundColor(.secondary)
            
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
                    AxisMarks(position: .leading)
                }
                .chartOverlay { proxy in
                    GeometryReader { geometry in
                        Rectangle()
                            .fill(Color.clear)
                            .contentShape(Rectangle())
                            .onTapGesture { location in
                                guard let plotFrameAnchor = proxy.plotFrame else { return }
                                let plotFrame = geometry[plotFrameAnchor]
                                let tapX = location.x - plotFrame.origin.x
                                
                                // Find closest data point
                                guard chartData.count > 1 else { return }
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
            
            legend
        }
        .padding()
        .background(Color(UIColor.secondarySystemBackground))
        .cornerRadius(12)
    }
} 