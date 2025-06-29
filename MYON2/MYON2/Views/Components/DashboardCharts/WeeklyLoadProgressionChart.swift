import SwiftUI
import Charts

struct WeeklyLoadProgressionChart: View {
    let stats: [WeeklyStats]
    
    // Data series for each metric
    private var chartData: [(week: String, metric: String, value: Double)] {
        let limitedStats = Array(stats.suffix(8))
        var data: [(String, String, Double)] = []
        
        for stat in limitedStats {
            let weekLabel = DashboardDataTransformer.formatWeekLabel(stat.id)
            
            // Weight (normalize if needed)
            let weight = stat.totalWeight > 10000 ? stat.totalWeight / 1000 : stat.totalWeight
            data.append((weekLabel, "Load", weight))
            
            // Sets
            data.append((weekLabel, "Sets", Double(stat.totalSets)))
            
            // Reps (scale down for visibility)
            data.append((weekLabel, "Reps", Double(stat.totalReps) / 10))
        }
        
        return data
    }
    
    private var isWeightNormalized: Bool {
        stats.contains { $0.totalWeight > 10000 }
    }
    
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text("Weekly Load Progression")
                    .font(.headline)
                    .foregroundColor(.secondary)
                
                if isWeightNormalized {
                    Text("Load values shown in tons (×1000 kg)")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }
            }
            
            Chart(chartData, id: \.0) { dataPoint in
                LineMark(
                    x: .value("Week", dataPoint.week),
                    y: .value("Value", dataPoint.value)
                )
                .foregroundStyle(by: .value("Metric", dataPoint.metric))
                .symbol(by: .value("Metric", dataPoint.metric))
                .symbolSize(80)
                
                PointMark(
                    x: .value("Week", dataPoint.week),
                    y: .value("Value", dataPoint.value)
                )
                .foregroundStyle(by: .value("Metric", dataPoint.metric))
            }
            .frame(height: 250)
            .chartForegroundStyleScale([
                "Load": Color.blue,
                "Sets": Color.green,
                "Reps": Color.orange
            ])
            .chartSymbolScale([
                "Load": Circle(),
                "Sets": Square(),
                "Reps": Diamond()
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
                    AxisValueLabel {
                        if let val = value.as(Double.self) {
                            Text(formatAxisValue(val))
                                .font(.caption)
                        }
                    }
                    AxisGridLine()
                }
            }
            .chartLegend(position: .bottom, alignment: .center) {
                HStack(spacing: 16) {
                    ForEach(["Load", "Sets", "Reps"], id: \.self) { metric in
                        HStack(spacing: 4) {
                            Image(systemName: symbolForMetric(metric))
                                .foregroundColor(colorForMetric(metric))
                                .font(.caption)
                            Text(legendLabelForMetric(metric))
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
    
    private func formatAxisValue(_ value: Double) -> String {
        if value >= 1000 {
            return String(format: "%.0fk", value / 1000)
        }
        return String(format: "%.0f", value)
    }
    
    private func symbolForMetric(_ metric: String) -> String {
        switch metric {
        case "Load": return "circle.fill"
        case "Sets": return "square.fill"
        case "Reps": return "diamond.fill"
        default: return "circle.fill"
        }
    }
    
    private func colorForMetric(_ metric: String) -> Color {
        switch metric {
        case "Load": return .blue
        case "Sets": return .green
        case "Reps": return .orange
        default: return .gray
        }
    }
    
    private func legendLabelForMetric(_ metric: String) -> String {
        switch metric {
        case "Load": return isWeightNormalized ? "Load (tons)" : "Load (kg)"
        case "Sets": return "Sets"
        case "Reps": return "Reps (÷10)"
        default: return metric
        }
    }
} 