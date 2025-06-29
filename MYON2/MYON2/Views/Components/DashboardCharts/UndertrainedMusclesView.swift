import SwiftUI

struct UndertrainedMusclesView: View {
    let stats: [WeeklyStats]
    
    // Aggregate muscle data from last 4 weeks
    private var aggregatedMuscleData: [(muscle: String, weight: Double, sets: Int, reps: Int)] {
        let recentStats = Array(stats.suffix(4))
        var muscleAggregates: [String: (weight: Double, sets: Int, reps: Int)] = [:]
        
        // Aggregate data across weeks
        for stat in recentStats {
            // Include all muscles that appear in any metric
            let allMuscles = Set(
                Array(stat.weightPerMuscle?.keys ?? []) +
                Array(stat.setsPerMuscle?.keys ?? []) +
                Array(stat.repsPerMuscle?.keys ?? [])
            )
            
            for muscle in allMuscles {
                let weight = stat.weightPerMuscle?[muscle] ?? 0
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
        
        // Convert to array and sort
        return muscleAggregates.map { muscle, data in
            (muscle.capitalized, data.weight, data.sets, data.reps)
        }
        .sorted { $0.weight < $1.weight } // Sort by lowest volume first
    }
    
    private var undertrainedMuscles: [(muscle: String, weight: Double, sets: Int, reps: Int)] {
        aggregatedMuscleData.filter { muscle in
            muscle.sets < UndertrainedThresholds.minSets || 
            muscle.weight < UndertrainedThresholds.minWeight
        }
    }
    
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text("Training Balance")
                        .font(.headline)
                        .foregroundColor(.primary)
                    
                    Spacer()
                    
                    if undertrainedMuscles.isEmpty {
                        Image(systemName: "checkmark.circle.fill")
                            .foregroundColor(.green)
                            .font(.subheadline)
                    } else {
                        Image(systemName: "exclamationmark.triangle.fill")
                            .foregroundColor(.orange)
                            .font(.subheadline)
                    }
                }
                
                Text("Muscle training analysis (last 4 weeks)")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            
            if undertrainedMuscles.isEmpty {
                VStack(spacing: 12) {
                    Image(systemName: "star.fill")
                        .font(.largeTitle)
                        .foregroundColor(.green)
                    
                    Text("Great balance!")
                        .font(.headline)
                        .foregroundColor(.primary)
                    
                    Text("All muscles meet minimum training thresholds")
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 30)
            } else {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Consider training these muscles more:")
                        .font(.caption)
                        .foregroundColor(.secondary)
                    
                    // Show up to 5 undertrained muscles
                    ForEach(undertrainedMuscles.prefix(5), id: \.muscle) { muscle in
                        HStack {
                            HStack(spacing: 8) {
                                Circle()
                                    .fill(Color.orange.opacity(0.2))
                                    .overlay(
                                        Circle()
                                            .stroke(Color.orange, lineWidth: 1)
                                    )
                                    .frame(width: 6, height: 6)
                                
                                Text(muscle.muscle)
                                    .font(.subheadline)
                                    .foregroundColor(.primary)
                            }
                            
                            Spacer()
                            
                            HStack(spacing: 12) {
                                HStack(spacing: 4) {
                                    if muscle.sets < UndertrainedThresholds.minSets {
                                        Image(systemName: "exclamationmark.circle.fill")
                                            .font(.caption2)
                                            .foregroundColor(.orange)
                                    }
                                    Text("\(muscle.sets) sets")
                                        .font(.caption)
                                        .foregroundColor(muscle.sets < UndertrainedThresholds.minSets ? .orange : .secondary)
                                }
                                
                                HStack(spacing: 4) {
                                    if muscle.weight < UndertrainedThresholds.minWeight {
                                        Image(systemName: "exclamationmark.circle.fill")
                                            .font(.caption2)
                                            .foregroundColor(.orange)
                                    }
                                    Text(formatWeight(muscle.weight))
                                        .font(.caption)
                                        .foregroundColor(muscle.weight < UndertrainedThresholds.minWeight ? .orange : .secondary)
                                }
                            }
                        }
                        .padding(.vertical, 4)
                    }
                    
                    if undertrainedMuscles.count > 5 {
                        Text("... and \(undertrainedMuscles.count - 5) more")
                            .font(.caption)
                            .foregroundColor(.secondary)
                            .padding(.top, 4)
                    }
                    
                    // Thresholds info
                    HStack(spacing: 16) {
                        Label("Goal: 4+ sets", systemImage: "info.circle")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                        
                        Label("Goal: 500+ kg", systemImage: "info.circle")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                    }
                    .padding(.top, 8)
                }
                .padding(.vertical, 8)
            }
        }
        .padding()
        .background(Color(UIColor.secondarySystemBackground))
        .cornerRadius(12)
    }
    
    private func formatWeight(_ weight: Double) -> String {
        String(format: "%.0f kg", weight)
    }
} 