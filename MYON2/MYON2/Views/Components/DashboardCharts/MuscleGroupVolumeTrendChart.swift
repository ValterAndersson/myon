import SwiftUI
import Charts

struct MuscleGroupVolumeTrendChart: View {
    let stats: [WeeklyStats]
    
    // Transform data for stacked bars
    private var chartData: [(week: String, group: MuscleGroup, volume: Double)] {
        let muscleGroupData = DashboardDataTransformer.transformToMuscleGroupData(Array(stats.suffix(8)))
        var data: [(String, MuscleGroup, Double)] = []
        
        for weekData in muscleGroupData {
            let weekLabel = DashboardDataTransformer.formatWeekLabel(weekData.weekId)
            
            for group in MuscleGroup.allCases {
                let volume = weekData.groupVolumes[group] ?? 0
                if volume > 0 { // Only include groups with volume
                    data.append((weekLabel, group, volume))
                }
            }
        }
        
        return data
    }
    
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Muscle Group Volume Trend")
                .font(.headline)
                .foregroundColor(.secondary)
            
            Chart(chartData, id: \.week) { dataPoint in
                BarMark(
                    x: .value("Week", dataPoint.week),
                    y: .value("Volume", dataPoint.volume)
                )
                .foregroundStyle(by: .value("Group", dataPoint.group.rawValue))
                .position(by: .value("Group", dataPoint.group.rawValue))
            }
            .frame(height: 250)
            .chartForegroundStyleScale(
                domain: MuscleGroup.allCases.map { $0.rawValue },
                range: MuscleGroup.allCases.map { $0.color }
            )
            .chartXAxis {
                AxisMarks(values: .automatic) { _ in
                    AxisValueLabel()
                        .font(.caption)
                    AxisGridLine()
                }
            }
            .chartYAxis {
                AxisMarks(position: .leading) { value in
                    AxisValueLabel {
                        if let val = value.as(Double.self) {
                            Text(formatVolume(val))
                                .font(.caption)
                        }
                    }
                    AxisGridLine()
                }
            }
            .chartLegend(position: .bottom, alignment: .center, spacing: 8) {
                HStack(spacing: 12) {
                    ForEach(MuscleGroup.allCases, id: \.self) { group in
                        HStack(spacing: 4) {
                            Circle()
                                .fill(group.color)
                                .frame(width: 8, height: 8)
                            Text(group.rawValue)
                                .font(.caption)
                                .foregroundColor(.primary)
                        }
                    }
                }
            }
        }
        .padding()
        .background(Color(UIColor.secondarySystemBackground))
        .cornerRadius(12)
    }
    
    private func formatVolume(_ value: Double) -> String {
        if value >= 1000 {
            return String(format: "%.0fk", value / 1000)
        }
        return String(format: "%.0f", value)
    }
} 