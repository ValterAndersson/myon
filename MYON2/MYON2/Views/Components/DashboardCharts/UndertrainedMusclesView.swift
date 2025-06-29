import SwiftUI

struct UndertrainedMusclesView: View {
    let currentWeekStats: WeeklyStats?
    
    private var undertrainedMuscles: [MuscleVolumeData] {
        DashboardDataTransformer.getUndertrainedMuscles(from: currentWeekStats)
    }
    
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Undertrained Muscles")
                    .font(.headline)
                    .foregroundColor(.secondary)
                
                Spacer()
                
                Image(systemName: "exclamationmark.triangle.fill")
                    .foregroundColor(.orange)
                    .font(.subheadline)
            }
            
            if undertrainedMuscles.isEmpty {
                HStack {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundColor(.green)
                        .font(.title2)
                    
                    Text("All muscles meet minimum training thresholds")
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 20)
                .background(Color(UIColor.tertiarySystemBackground))
                .cornerRadius(8)
            } else {
                VStack(alignment: .leading, spacing: 8) {
                    // Header
                    HStack(spacing: 0) {
                        Text("Muscle")
                            .font(.caption)
                            .foregroundColor(.secondary)
                            .frame(maxWidth: .infinity, alignment: .leading)
                        
                        Text("Sets")
                            .font(.caption)
                            .foregroundColor(.secondary)
                            .frame(width: 60, alignment: .trailing)
                        
                        Text("Weight")
                            .font(.caption)
                            .foregroundColor(.secondary)
                            .frame(width: 80, alignment: .trailing)
                        
                        Text("Reps")
                            .font(.caption)
                            .foregroundColor(.secondary)
                            .frame(width: 60, alignment: .trailing)
                    }
                    .padding(.horizontal, 4)
                    .padding(.bottom, 4)
                    
                    Divider()
                    
                    // Muscle rows
                    ForEach(undertrainedMuscles.prefix(10)) { muscle in
                        UndertrainedMuscleRow(muscle: muscle)
                    }
                    
                    if undertrainedMuscles.count > 10 {
                        Text("... and \(undertrainedMuscles.count - 10) more")
                            .font(.caption)
                            .foregroundColor(.secondary)
                            .padding(.top, 4)
                    }
                }
                .padding(.vertical, 8)
                
                // Thresholds info
                HStack(spacing: 16) {
                    Label("Min: 4 sets", systemImage: "info.circle")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                    
                    Label("Min: 500 kg", systemImage: "info.circle")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }
                .padding(.top, 8)
            }
        }
        .padding()
        .background(Color(UIColor.secondarySystemBackground))
        .cornerRadius(12)
    }
}

struct UndertrainedMuscleRow: View {
    let muscle: MuscleVolumeData
    
    private var isSetsLow: Bool { muscle.sets < UndertrainedThresholds.minSets }
    private var isWeightLow: Bool { muscle.weight < UndertrainedThresholds.minWeight }
    
    var body: some View {
        HStack(spacing: 0) {
            // Muscle name with group color
            HStack(spacing: 8) {
                Circle()
                    .fill(muscle.group?.color ?? Color.gray)
                    .frame(width: 6, height: 6)
                
                Text(muscle.muscleName)
                    .font(.subheadline)
                    .foregroundColor(.primary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            
            // Sets
            HStack(spacing: 4) {
                if isSetsLow {
                    Image(systemName: "exclamationmark.circle.fill")
                        .font(.caption2)
                        .foregroundColor(.orange)
                }
                Text("\(muscle.sets)")
                    .font(.subheadline)
                    .foregroundColor(isSetsLow ? .orange : .primary)
            }
            .frame(width: 60, alignment: .trailing)
            
            // Weight
            HStack(spacing: 4) {
                if isWeightLow {
                    Image(systemName: "exclamationmark.circle.fill")
                        .font(.caption2)
                        .foregroundColor(.orange)
                }
                Text(formatWeight(muscle.weight))
                    .font(.subheadline)
                    .foregroundColor(isWeightLow ? .orange : .primary)
            }
            .frame(width: 80, alignment: .trailing)
            
            // Reps
            Text("\(muscle.reps)")
                .font(.subheadline)
                .foregroundColor(.secondary)
                .frame(width: 60, alignment: .trailing)
        }
        .padding(.horizontal, 4)
        .padding(.vertical, 4)
    }
    
    private func formatWeight(_ weight: Double) -> String {
        String(format: "%.0f kg", weight)
    }
} 