import SwiftUI
import Charts

// MARK: - Chart Theme
struct ChartTheme {
    static let primaryGradient = LinearGradient(
        colors: [.blue, .blue.opacity(0.3)],
        startPoint: .top,
        endPoint: .bottom
    )
    
    static let secondaryGradient = LinearGradient(
        colors: [.green, .green.opacity(0.3)],
        startPoint: .top,
        endPoint: .bottom
    )
    
    static let accentGradient = LinearGradient(
        colors: [.orange, .orange.opacity(0.3)],
        startPoint: .top,
        endPoint: .bottom
    )
}

// MARK: - Dashboard Specific Charts

struct WorkoutFrequencyChart: View {
    let stats: [WeeklyStats]
    let goal: Int?
    
    private var maxValue: Double {
        let maxWorkouts = stats.map { Double($0.workouts) }.max() ?? 0
        return max(maxWorkouts, Double(goal ?? 0)) + 1
    }
    
    var body: some View {
        Chart {
            ForEach(stats, id: \.id) { stat in
                BarMark(
                    x: .value("Week", formatWeekLabel(stat.id)),
                    y: .value("Workouts", stat.workouts)
                )
                .foregroundStyle(ChartTheme.primaryGradient)
                .cornerRadius(4)
            }
            
            if let goal = goal {
                RuleMark(y: .value("Goal", goal))
                    .foregroundStyle(.red.opacity(0.7))
                    .lineStyle(StrokeStyle(lineWidth: 2, dash: [5, 5]))
                    .annotation(position: .topTrailing, alignment: .trailing) {
                        Text("Goal: \(goal)")
                            .font(.caption)
                            .foregroundColor(.red)
                            .padding(.horizontal, 4)
                    }
            }
        }
        .chartYScale(domain: 0...maxValue)
        .chartXAxis {
            AxisMarks(values: .automatic) { _ in
                AxisValueLabel()
                    .font(.caption)
            }
        }
        .chartYAxis {
            AxisMarks(position: .leading)
        }
        .frame(height: 200)
    }
    
    private func formatWeekLabel(_ weekId: String) -> String {
        // Convert YYYY-MM-DD to MM/DD
        let components = weekId.split(separator: "-")
        guard components.count == 3 else { return weekId }
        return "\(components[1])/\(components[2])"
    }
}

struct VolumeByMuscleGroupChart: View {
    let stats: [WeeklyStats]

    private var muscleGroups: [String] {
        let allGroups = Set(stats.flatMap { stat in 
            stat.weightPerMuscleGroup?.keys ?? []
        })
        return Array(allGroups).sorted()
    }
    
    private var chartData: [(week: String, group: String, volume: Double)] {
        var data: [(week: String, group: String, volume: Double)] = []
        
        for stat in stats {
            let weekLabel = formatWeekLabel(stat.id)
            for group in muscleGroups {
                let volume = stat.weightPerMuscleGroup?[group] ?? 0
                if volume > 0 {
                    data.append((week: weekLabel, group: group, volume: volume))
                }
            }
        }
        
        return data
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if !muscleGroups.isEmpty {
                Chart(chartData, id: \.week) { item in
                    BarMark(
                        x: .value("Week", item.week),
                        y: .value("Volume", item.volume)
                    )
                    .foregroundStyle(by: .value("Muscle Group", item.group))
                    .position(by: .value("Muscle Group", item.group))
                }
                .chartXAxis {
                    AxisMarks(values: .automatic) { _ in
                        AxisValueLabel()
                            .font(.caption)
                    }
                }
                .chartYAxis {
                    AxisMarks(position: .leading) { value in
                        AxisGridLine()
                        AxisValueLabel {
                            if let volume = value.as(Double.self) {
                                Text("\(Int(volume))kg")
                                    .font(.caption)
                            }
                        }
                    }
                }
                .chartLegend(position: .bottom, alignment: .center)
                .frame(height: 250)
            } else {
                Text("No muscle group data available")
                    .foregroundColor(.secondary)
                    .frame(height: 250)
                    .frame(maxWidth: .infinity)
            }
        }
    }
    
    private func formatWeekLabel(_ weekId: String) -> String {
        let components = weekId.split(separator: "-")
        guard components.count == 3 else { return weekId }
        return "\(components[1])/\(components[2])"
    }
}

struct VolumeByMuscleChart: View {
    let stats: [WeeklyStats]

    private var muscles: [String] {
        let allMuscles = Set(stats.flatMap { stat in 
            stat.weightPerMuscle?.keys ?? []
        })
        return Array(allMuscles).sorted()
    }
    
    private var latestVolumes: [(muscle: String, volume: Double)] {
        guard let latestStats = stats.first,
              let volumes = latestStats.weightPerMuscle else { return [] }
        
        return volumes.map { (muscle: $0.key, volume: $0.value) }
            .sorted { $0.volume > $1.volume }
            .prefix(10) // Show top 10 muscles
            .map { $0 }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if !latestVolumes.isEmpty {
                Chart(latestVolumes, id: \.muscle) { item in
                    BarMark(
                        x: .value("Volume", item.volume),
                        y: .value("Muscle", item.muscle)
                    )
                    .foregroundStyle(ChartTheme.accentGradient)
                    .cornerRadius(4)
                }
                .chartXAxis {
                    AxisMarks(position: .bottom) { value in
                        AxisGridLine()
                        AxisValueLabel {
                            if let volume = value.as(Double.self) {
                                Text("\(Int(volume))kg")
                                    .font(.caption)
                            }
                        }
                    }
                }
                .frame(height: CGFloat(latestVolumes.count * 35 + 50))
            } else {
                Text("No muscle volume data available")
                    .foregroundColor(.secondary)
                    .frame(height: 200)
                    .frame(maxWidth: .infinity)
            }
        }
    }
}

struct SetsRepsChart: View {
    let stats: [WeeklyStats]
    
    private var chartData: [(week: String, sets: Int, reps: Int)] {
        stats.map { stat in
            let weekLabel = formatWeekLabel(stat.id)
            return (week: weekLabel, sets: stat.totalSets, reps: stat.totalReps)
        }
    }

    var body: some View {
        Chart {
            // Sets bars
            ForEach(chartData, id: \.week) { item in
                BarMark(
                    x: .value("Week", item.week),
                    y: .value("Sets", item.sets)
                )
                .foregroundStyle(ChartTheme.secondaryGradient)
                .cornerRadius(4)
            }
            
            // Reps line
            ForEach(chartData, id: \.week) { item in
                LineMark(
                    x: .value("Week", item.week),
                    y: .value("Reps", item.reps / 10) // Scale down reps for better visualization
                )
                .foregroundStyle(.orange)
                .lineStyle(StrokeStyle(lineWidth: 3))
                .symbol {
                    Circle()
                        .fill(.orange)
                        .frame(width: 8, height: 8)
                }
            }
        }
        .chartXAxis {
            AxisMarks(values: .automatic) { _ in
                AxisValueLabel()
                    .font(.caption)
            }
        }
        .chartYAxis {
            AxisMarks(position: .leading) { value in
                AxisGridLine()
                AxisValueLabel {
                    if let val = value.as(Int.self) {
                        Text("\(val)")
                            .font(.caption)
                    }
                }
            }
        }
        .chartYAxis(.trailing) {
            AxisMarks(position: .trailing) { value in
                AxisValueLabel {
                    if let val = value.as(Int.self) {
                        Text("\(val * 10)")
                            .font(.caption)
                            .foregroundColor(.orange)
                    }
                }
            }
        }
        .frame(height: 220)
        .overlay(alignment: .topTrailing) {
            VStack(alignment: .leading, spacing: 4) {
                Label("Sets", systemImage: "square.fill")
                    .foregroundColor(.green)
                    .font(.caption)
                Label("Reps (×10)", systemImage: "line.diagonal")
                    .foregroundColor(.orange)
                    .font(.caption)
            }
            .padding(8)
            .background(Color(UIColor.systemBackground).opacity(0.9))
            .cornerRadius(8)
            .padding()
        }
    }
    
    private func formatWeekLabel(_ weekId: String) -> String {
        let components = weekId.split(separator: "-")
        guard components.count == 3 else { return weekId }
        return "\(components[1])/\(components[2])"
    }
}

