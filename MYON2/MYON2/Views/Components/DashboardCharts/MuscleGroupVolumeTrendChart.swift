import SwiftUI
import Charts

// Data model for chart points
private struct ChartDataPoint: Identifiable {
    let id = UUID()
    let week: String
    let group: MuscleGroup
    let volume: Double
}

struct MuscleGroupVolumeTrendChart: View {
    let stats: [WeeklyStats]
    @State private var selectedGroup: MuscleGroup?
    @State private var selectedWeekId: String?
    @State private var showGroupBreakdown = false
    
    // Use last 4 weeks (oldest to newest)
    private var chartData: [ChartDataPoint] {
        let muscleGroupData = DashboardDataTransformer.transformToMuscleGroupData(Array(stats.suffix(4).reversed()))
        var data: [ChartDataPoint] = []
        
        for weekData in muscleGroupData {
            let weekLabel = DashboardDataTransformer.formatWeekLabel(weekData.weekId)
            
            for group in MuscleGroup.allCases {
                let volume = weekData.groupVolumes[group] ?? 0
                if volume > 0 { // Only include groups with volume
                    data.append(ChartDataPoint(week: weekLabel, group: group, volume: volume))
                }
            }
        }
        
        return data
    }
    
    private let groupNames = MuscleGroup.allCases.map { $0.rawValue }
    private let groupColors = MuscleGroup.allCases.map { $0.color }
    
    @ViewBuilder
    private var chartView: some View {
        Chart(chartData) { dataPoint in
            BarMark(
                x: .value("Week", dataPoint.week),
                y: .value("Volume", dataPoint.volume)
            )
            .foregroundStyle(by: .value("Group", dataPoint.group.rawValue))
        }
        .frame(height: 250)
        .chartForegroundStyleScale(
            domain: groupNames,
            range: groupColors
        )
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
                        Text(formatVolume(val))
                            .font(.caption)
                    }
                }
                AxisGridLine()
            }
        }
        .chartBackground { proxy in
            GeometryReader { geometry in
                Rectangle()
                    .fill(Color.clear)
                    .contentShape(Rectangle())
                    .onTapGesture { location in
                        handleTap(location: location, proxy: proxy, geometry: geometry)
                    }
            }
        }
    }
    
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            VStack(alignment: .leading, spacing: 4) {
                Text("Muscle Group Volume Trend")
                    .font(.headline)
                    .foregroundColor(.primary)
                
                Text("Total weight by muscle group (last 4 weeks)")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            
            chartView
        }
        .padding()
        .background(Color(UIColor.secondarySystemBackground))
        .cornerRadius(12)
        .sheet(isPresented: $showGroupBreakdown) {
            if let weekId = selectedWeekId, let group = selectedGroup {
                MuscleGroupBreakdownView(weekId: weekId, muscleGroup: group, allStats: stats)
            }
        }
    }
    
    private func handleTap(location: CGPoint, proxy: ChartProxy, geometry: GeometryProxy) {
        guard let plotFrameAnchor = proxy.plotFrame else { return }
        let plotFrame = geometry[plotFrameAnchor]
        
        // Determine which week was tapped
        let weekCount = 4
        let barWidth = plotFrame.width / CGFloat(weekCount)
        let weekIndex = Int(location.x / barWidth)
        
                    if weekIndex >= 0 && weekIndex < weekCount {
                // Get the week ID (remember chart is now oldest to newest)
                let weekStats = Array(stats.suffix(4).reversed())
                if weekIndex < weekStats.count {
                    let weekId = weekStats[weekIndex].id
                
                // Determine which muscle group based on Y position
                let relativeY = (plotFrame.height - (location.y - plotFrame.origin.y)) / plotFrame.height
                
                // Find which group was tapped based on stacked position
                if let tappedGroup = findTappedGroup(at: relativeY, weekId: weekId) {
                    selectedWeekId = weekId
                    selectedGroup = tappedGroup
                    showGroupBreakdown = true
                }
            }
        }
    }
    
    private func formatVolume(_ value: Double) -> String {
        if value >= 1000 {
            return String(format: "%.0fk", value / 1000)
        }
        return String(format: "%.0f", value)
    }
    
    private func findTappedGroup(at relativeY: Double, weekId: String) -> MuscleGroup? {
        // Get the week's data
        guard let weekStats = stats.first(where: { $0.id == weekId }) else { return nil }
        let groupData = DashboardDataTransformer.transformToMuscleGroupData([weekStats]).first
        
        // Calculate cumulative heights
        var cumulativeHeight = 0.0
        let totalVolume = MuscleGroup.allCases.compactMap { groupData?.groupVolumes[$0] }.reduce(0, +)
        
        guard totalVolume > 0 else { return nil }
        
        for group in MuscleGroup.allCases {
            let volume = groupData?.groupVolumes[group] ?? 0
            let proportion = volume / totalVolume
            
            if relativeY >= cumulativeHeight && relativeY <= cumulativeHeight + proportion {
                return group
            }
            
            cumulativeHeight += proportion
        }
        
        return nil
    }
}

// MARK: - Muscle Group Breakdown View
struct MuscleGroupBreakdownView: View {
    let weekId: String
    let muscleGroup: MuscleGroup
    let allStats: [WeeklyStats] // Accept stats from parent
    @Environment(\.dismiss) private var dismiss
    
    private var exercises: [(muscle: String, sets: Int, reps: Int, weight: Double)] {
        guard let weekStats = allStats.first(where: { $0.id == weekId }) else { return [] }
        
        var result: [(muscle: String, sets: Int, reps: Int, weight: Double)] = []
        
        for muscle in muscleGroup.muscles {
            let sets = weekStats.setsPerMuscle?[muscle] ?? 0
            let reps = weekStats.repsPerMuscle?[muscle] ?? 0
            let weight = weekStats.weightPerMuscle?[muscle] ?? 0
            
            if sets > 0 || reps > 0 || weight > 0 {
                result.append((muscle: muscle.capitalized, sets: sets, reps: reps, weight: weight))
            }
        }
        
        return result.sorted { $0.weight > $1.weight }
    }
    
    var body: some View {
        NavigationStack {
            List {
                Section {
                    ForEach(exercises, id: \.muscle) { exercise in
                        HStack {
                            Text(exercise.muscle)
                                .foregroundColor(.primary)
                            
                            Spacer()
                            
                            VStack(alignment: .trailing, spacing: 2) {
                                Text(formatWeight(exercise.weight))
                                    .font(.subheadline).bold()
                                HStack(spacing: 8) {
                                    Text("\(exercise.sets) sets")
                                        .font(.caption)
                                        .foregroundColor(.secondary)
                                    Text("\(exercise.reps) reps")
                                        .font(.caption)
                                        .foregroundColor(.secondary)
                                }
                            }
                        }
                        .padding(.vertical, 4)
                    }
                } header: {
                    VStack(alignment: .leading) {
                        Text("\(muscleGroup.rawValue) - Week of \(DashboardDataTransformer.formatWeekLabel(weekId))")
                            .font(.headline)
                        Text("Muscle contributions to volume")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }
            }
            .navigationTitle("Volume Breakdown")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Close") { dismiss() }
                }
            }
        }
    }
    
    private func formatWeight(_ weight: Double) -> String {
        if weight >= 1000 {
            return String(format: "%.1fk kg", weight / 1000)
        }
        return String(format: "%.0f kg", weight)
    }
} 