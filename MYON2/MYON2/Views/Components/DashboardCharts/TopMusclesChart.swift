import SwiftUI
import Charts

struct TopMusclesChart: View {
    let stats: [WeeklyStats]
    @State private var showAllMuscles = false
    
    // Aggregate muscle data from last 4 weeks
    private var aggregatedMuscleData: [MuscleVolumeData] {
        let recentStats = Array(stats.suffix(4))
        var muscleAggregates: [String: (weight: Double, sets: Int, reps: Int)] = [:]
        
        // Aggregate data across weeks
        for stat in recentStats {
            if let weightPerMuscle = stat.weightPerMuscle {
                for (muscle, weight) in weightPerMuscle {
                    let sets = stat.setsPerMuscle?[muscle] ?? 0
                    let reps = stat.repsPerMuscle?[muscle] ?? 0
                    
                    if var existing = muscleAggregates[muscle] {
                        existing.weight += weight
                        existing.sets += sets
                        existing.reps += reps
                        muscleAggregates[muscle] = existing
                    } else {
                        muscleAggregates[muscle] = (weight, sets, reps)
                    }
                }
            }
        }
        
        // Convert to MuscleVolumeData
        return muscleAggregates.map { muscle, data in
            MuscleVolumeData(
                muscleName: muscle.capitalized,
                weight: data.weight,
                sets: data.sets,
                reps: data.reps
            )
        }
        .sorted { $0.weight > $1.weight }
    }
    
    private var topMuscles: [MuscleVolumeData] {
        Array(aggregatedMuscleData.prefix(5))
    }
    
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text("Top 5 Muscles by Volume")
                    .font(.headline)
                    .foregroundColor(.primary)
                
                Text("Based on last 4 weeks")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            
            if topMuscles.isEmpty {
                Text("No muscle data available")
                    .font(.subheadline)
                    .foregroundColor(.secondary)
                    .frame(height: 200)
                    .frame(maxWidth: .infinity)
                    .background(Color(UIColor.tertiarySystemBackground))
                    .cornerRadius(8)
            } else {
                VStack(spacing: 12) {
                    ForEach(topMuscles) { muscle in
                        HStack(spacing: 0) {
                            // Muscle name and group color indicator
                            HStack(spacing: 8) {
                                Circle()
                                    .fill(muscle.group?.color ?? Color.gray)
                                    .frame(width: 8, height: 8)
                                
                                Text(muscle.muscleName)
                                    .font(.subheadline)
                                    .foregroundColor(.primary)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                            }
                            .frame(width: 140)
                            
                            // Volume bar
                            HStack(spacing: 0) {
                                GeometryReader { geometry in
                                    ZStack(alignment: .leading) {
                                        // Background
                                        RoundedRectangle(cornerRadius: 4)
                                            .fill(Color(UIColor.tertiarySystemBackground))
                                        
                                        // Bar
                                        RoundedRectangle(cornerRadius: 4)
                                            .fill(muscle.group?.color.opacity(0.8) ?? Color.gray.opacity(0.8))
                                            .frame(width: barWidth(for: muscle.weight, in: geometry.size.width))
                                    }
                                }
                                .frame(height: 30)
                                
                                // Stats
                                VStack(alignment: .trailing, spacing: 2) {
                                    Text(formatWeight(muscle.weight))
                                        .font(.caption).bold()
                                        .foregroundColor(.primary)
                                    
                                    HStack(spacing: 8) {
                                        Text("\(muscle.sets) sets")
                                            .font(.caption2)
                                            .foregroundColor(.secondary)
                                        
                                        Text("\(muscle.reps) reps")
                                            .font(.caption2)
                                            .foregroundColor(.secondary)
                                    }
                                }
                                .padding(.leading, 8)
                            }
                        }
                    }
                }
                .padding(.vertical, 8)
                
                // Action button
                Button(action: { showAllMuscles = true }) {
                    Label("Show All Muscles", systemImage: "list.bullet")
                        .font(.subheadline)
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
                .padding(.top, 4)
            }
        }
        .padding()
        .background(Color(UIColor.secondarySystemBackground))
        .cornerRadius(12)
        .navigationDestination(isPresented: $showAllMuscles) {
            AllMusclesTableView(stats: stats)
        }
    }
    
    private func barWidth(for weight: Double, in maxWidth: CGFloat) -> CGFloat {
        guard let maxWeight = topMuscles.first?.weight, maxWeight > 0 else { return 0 }
        let ratio = weight / maxWeight
        return maxWidth * CGFloat(ratio)
    }
    
    private func formatWeight(_ weight: Double) -> String {
        if weight >= 1000 {
            return String(format: "%.1fk kg", weight / 1000)
        }
        return String(format: "%.0f kg", weight)
    }
}

// MARK: - All Muscles Table View
struct AllMusclesTableView: View {
    let stats: [WeeklyStats]
    @Environment(\.dismiss) private var dismiss
    @State private var sortOption: SortOption = .volume
    
    enum SortOption: String, CaseIterable {
        case volume = "Volume"
        case sets = "Sets"
        case name = "Name"
    }
    
    // Aggregate muscle data from last 4 weeks
    private var aggregatedMuscleData: [MuscleVolumeData] {
        let recentStats = Array(stats.suffix(4))
        var muscleAggregates: [String: (weight: Double, sets: Int, reps: Int)] = [:]
        
        // Aggregate data across weeks
        for stat in recentStats {
            if let weightPerMuscle = stat.weightPerMuscle {
                for (muscle, weight) in weightPerMuscle {
                    let sets = stat.setsPerMuscle?[muscle] ?? 0
                    let reps = stat.repsPerMuscle?[muscle] ?? 0
                    
                    if var existing = muscleAggregates[muscle] {
                        existing.weight += weight
                        existing.sets += sets
                        existing.reps += reps
                        muscleAggregates[muscle] = existing
                    } else {
                        muscleAggregates[muscle] = (weight, sets, reps)
                    }
                }
            }
        }
        
        // Convert to MuscleVolumeData
        let data = muscleAggregates.map { muscle, data in
            MuscleVolumeData(
                muscleName: muscle.capitalized,
                weight: data.weight,
                sets: data.sets,
                reps: data.reps
            )
        }
        
        // Sort based on option
        switch sortOption {
        case .volume:
            return data.sorted { $0.weight > $1.weight }
        case .sets:
            return data.sorted { $0.sets > $1.sets }
        case .name:
            return data.sorted { $0.muscleName < $1.muscleName }
        }
    }
    
    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                // Sort picker
                Picker("Sort by", selection: $sortOption) {
                    ForEach(SortOption.allCases, id: \.self) { option in
                        Text(option.rawValue).tag(option)
                    }
                }
                .pickerStyle(.segmented)
                .padding()
                
                // Table header
                HStack {
                    Text("Muscle")
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                    
                    Text("Sets")
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .frame(width: 60, alignment: .trailing)
                    
                    Text("Reps")
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .frame(width: 60, alignment: .trailing)
                    
                    Text("Load")
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .frame(width: 80, alignment: .trailing)
                }
                .padding(.horizontal)
                .padding(.bottom, 8)
                
                Divider()
                
                // Table content
                List {
                    ForEach(aggregatedMuscleData) { muscle in
                        HStack {
                            HStack(spacing: 8) {
                                Circle()
                                    .fill(muscle.group?.color ?? Color.gray)
                                    .frame(width: 8, height: 8)
                                
                                Text(muscle.muscleName)
                                    .font(.subheadline)
                                    .foregroundColor(.primary)
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                            
                            Text("\(muscle.sets)")
                                .font(.subheadline)
                                .foregroundColor(.primary)
                                .frame(width: 60, alignment: .trailing)
                            
                            Text("\(muscle.reps)")
                                .font(.subheadline)
                                .foregroundColor(.primary)
                                .frame(width: 60, alignment: .trailing)
                            
                            Text(formatWeight(muscle.weight))
                                .font(.subheadline).bold()
                                .foregroundColor(.primary)
                                .frame(width: 80, alignment: .trailing)
                        }
                        .listRowBackground(Color.clear)
                        .listRowSeparator(.hidden)
                        .padding(.vertical, 4)
                    }
                }
                .listStyle(.plain)
            }
            .navigationTitle("All Muscles (Last 4 Weeks)")
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
            return String(format: "%.1fk", weight / 1000)
        }
        return String(format: "%.0f", weight)
    }
} 