import SwiftUI
import Charts

struct WeeklyLoadProgressionChart: View {
    let stats: [WeeklyStats]
    @State private var showSetsRepsDetail = false
    
    // Use last 4 weeks (oldest to newest)
    private var chartData: [WeeklyStats] {
        Array(stats.suffix(4).reversed())
    }
    
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text("Weekly Load Progression")
                    .font(.headline)
                    .foregroundColor(.primary)
                
                Text("Total weight lifted (last 4 weeks)")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            
            Chart(chartData) { stat in
                LineMark(
                    x: .value("Week", DashboardDataTransformer.formatWeekLabel(stat.id)),
                    y: .value("Load", stat.totalWeight)
                )
                .foregroundStyle(Color.blue)
                .symbol(.circle)
                .symbolSize(100)
                
                PointMark(
                    x: .value("Week", DashboardDataTransformer.formatWeekLabel(stat.id)),
                    y: .value("Load", stat.totalWeight)
                )
                .foregroundStyle(Color.blue)
                .annotation(position: .top) {
                    Text(formatWeight(stat.totalWeight))
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }
            }
            .frame(height: 200)
            .chartXAxis {
                AxisMarks(values: .automatic) { _ in
                    AxisValueLabel()
                        .font(.caption)
                    AxisGridLine()
                }
            }
            .chartYAxis {
                AxisMarks(position: .trailing) { value in
                    AxisValueLabel {
                        if let val = value.as(Double.self) {
                            Text(formatWeight(val))
                                .font(.caption)
                        }
                    }
                    AxisGridLine()
                }
            }
            
            // Action button
            Button(action: { showSetsRepsDetail = true }) {
                Label("View sets & reps", systemImage: "chart.line.uptrend.xyaxis")
                    .font(.subheadline)
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
        }
        .padding()
        .background(Color(UIColor.secondarySystemBackground))
        .cornerRadius(12)
        .sheet(isPresented: $showSetsRepsDetail) {
            SetsRepsDetailView(stats: chartData)
        }
    }
    
    private func formatWeight(_ value: Double) -> String {
        if value >= 1000 {
            return String(format: "%.1fk kg", value / 1000)
        }
        return String(format: "%.0f kg", value)
    }
}

// MARK: - Sets & Reps Detail View
struct SetsRepsDetailView: View {
    let stats: [WeeklyStats]
    @Environment(\.dismiss) private var dismiss
    
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 20) {
                    // Sets Chart
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Weekly Sets")
                            .font(.headline)
                            .foregroundColor(.primary)
                        
                        Chart(stats) { stat in
                            LineMark(
                                x: .value("Week", DashboardDataTransformer.formatWeekLabel(stat.id)),
                                y: .value("Sets", stat.totalSets)
                            )
                            .foregroundStyle(Color.green)
                            .symbol(.square)
                            .symbolSize(100)
                            
                            PointMark(
                                x: .value("Week", DashboardDataTransformer.formatWeekLabel(stat.id)),
                                y: .value("Sets", stat.totalSets)
                            )
                            .foregroundStyle(Color.green)
                        }
                        .frame(height: 180)
                    }
                    .padding()
                    .background(Color(UIColor.secondarySystemBackground))
                    .cornerRadius(12)
                    
                    // Reps Chart
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Weekly Reps")
                            .font(.headline)
                            .foregroundColor(.primary)
                        
                        Chart(stats) { stat in
                            LineMark(
                                x: .value("Week", DashboardDataTransformer.formatWeekLabel(stat.id)),
                                y: .value("Reps", stat.totalReps)
                            )
                            .foregroundStyle(Color.orange)
                            .symbol(.diamond)
                            .symbolSize(100)
                            
                            PointMark(
                                x: .value("Week", DashboardDataTransformer.formatWeekLabel(stat.id)),
                                y: .value("Reps", stat.totalReps)
                            )
                            .foregroundStyle(Color.orange)
                        }
                        .frame(height: 180)
                    }
                    .padding()
                    .background(Color(UIColor.secondarySystemBackground))
                    .cornerRadius(12)
                }
                .padding()
            }
            .navigationTitle("Sets & Reps Breakdown")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Close") { dismiss() }
                }
            }
        }
    }
} 