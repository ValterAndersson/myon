import SwiftUI
import Charts

// MARK: - Generic Chart Components

/// Simple bar chart that can optionally show a goal line
struct BarChart<DataPoint: Identifiable>: View {
    let data: [DataPoint]
    let xValue: (DataPoint) -> String
    let yValue: (DataPoint) -> Double
    var goal: Double?
    var height: CGFloat = 200

    private var maxValue: Double {
        max(data.map { yValue($0) }.max() ?? 0, goal ?? 0)
    }

    var body: some View {
        Chart {
            ForEach(data) { point in
                BarMark(
                    x: .value("X", xValue(point)),
                    y: .value("Value", yValue(point))
                )
            }
            if let goal = goal {
                RuleMark(y: .value("Goal", goal))
                    .foregroundStyle(.red)
                    .lineStyle(StrokeStyle(lineWidth: 2, dash: [5]))
            }
        }
        .chartYScale(domain: 0...(maxValue + 1))
        .frame(height: height)
    }
}

/// Stacked bar chart for grouped values
struct StackedBarChart<DataPoint: Identifiable, Group: Hashable>: View {
    let data: [DataPoint]
    let groups: [Group]
    let xValue: (DataPoint) -> String
    let value: (DataPoint, Group) -> Double
    var height: CGFloat = 220

    var body: some View {
        Chart {
            ForEach(data) { point in
                ForEach(groups, id: .self) { g in
                    let val = value(point, g)
                    if val > 0 {
                        BarMark(
                            x: .value("Week", xValue(point)),
                            y: .value("Value", val),
                            stacking: .standard
                        )
                        .foregroundStyle(by: .value("Group", String(describing: g)))
                    }
                }
            }
        }
        .frame(height: height)
    }
}

/// Combined bar and line chart used for sets vs reps
struct ComboBarLineChart<DataPoint: Identifiable>: View {
    let data: [DataPoint]
    let xValue: (DataPoint) -> String
    let barValue: (DataPoint) -> Double
    let lineValue: (DataPoint) -> Double
    var height: CGFloat = 220

    var body: some View {
        Chart {
            ForEach(data) { point in
                BarMark(
                    x: .value("Week", xValue(point)),
                    y: .value("Sets", barValue(point))
                )
                .foregroundStyle(.green.opacity(0.7))

                LineMark(
                    x: .value("Week", xValue(point)),
                    y: .value("Reps", lineValue(point))
                )
                .symbol(Circle())
                .foregroundStyle(.orange)
            }
        }
        .frame(height: height)
    }
}

// MARK: - Dashboard Specific Charts

struct WorkoutFrequencyChart: View {
    let stats: [WeeklyStats]
    let goal: Int?

    var body: some View {
        BarChart(
            data: stats,
            xValue: { $0.id },
            yValue: { Double($0.workouts) },
            goal: goal.map(Double.init)
        )
    }
}

struct VolumeByMuscleGroupChart: View {
    let stats: [WeeklyStats]

    private var muscleGroups: [String] {
        Set(stats.flatMap { $0.weightPerMuscleGroup?.keys ?? [] }).sorted()
    }

    var body: some View {
        StackedBarChart(
            data: stats,
            groups: muscleGroups,
            xValue: { $0.id },
            value: { week, group in week.weightPerMuscleGroup?[group] ?? 0 }
        )
    }
}

struct VolumeByMuscleChart: View {
    let stats: [WeeklyStats]

    private var muscles: [String] {
        Set(stats.flatMap { $0.weightPerMuscle?.keys ?? [] }).sorted()
    }

    var body: some View {
        StackedBarChart(
            data: stats,
            groups: muscles,
            xValue: { $0.id },
            value: { week, muscle in week.weightPerMuscle?[muscle] ?? 0 }
        )
    }
}

struct SetsRepsChart: View {
    let stats: [WeeklyStats]

    var body: some View {
        ComboBarLineChart(
            data: stats,
            xValue: { $0.id },
            barValue: { Double($0.totalSets) },
            lineValue: { Double($0.totalReps) }
        )
    }
}

