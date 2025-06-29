import SwiftUI
import Charts

struct TopMusclesChart: View {
    let currentWeekStats: WeeklyStats?
    
    private var topMuscles: [MuscleVolumeData] {
        DashboardDataTransformer.getTopMuscles(from: currentWeekStats, limit: 5)
    }
    
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Top 5 Muscles by Volume")
                .font(.headline)
                .foregroundColor(.secondary)
            
            if topMuscles.isEmpty {
                Text("No muscle data for this week")
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
            }
        }
        .padding()
        .background(Color(UIColor.secondarySystemBackground))
        .cornerRadius(12)
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