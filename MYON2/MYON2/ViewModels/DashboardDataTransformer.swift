import Foundation

class DashboardDataTransformer {
    
    // MARK: - Transform weekly stats to muscle group data
    static func transformToMuscleGroupData(_ stats: [WeeklyStats]) -> [WeeklyMuscleGroupData] {
        return stats.compactMap { stat in
            // Parse date from weekId
            let formatter = DateFormatter()
            formatter.dateFormat = "yyyy-MM-dd"
            formatter.timeZone = TimeZone(secondsFromGMT: 0)
            guard let date = formatter.date(from: stat.id) else { return nil }
            
            var groupVolumes: [MuscleGroup: Double] = [:]
            var groupSets: [MuscleGroup: Int] = [:]
            var groupReps: [MuscleGroup: Int] = [:]
            
            // Initialize all groups to 0
            for group in MuscleGroup.allCases {
                groupVolumes[group] = 0
                groupSets[group] = 0
                groupReps[group] = 0
            }
            
            // Aggregate weight by muscle group
            if let weightPerMuscle = stat.weightPerMuscle {
                for (muscle, weight) in weightPerMuscle {
                    if let group = MuscleGroup.fromMuscle(muscle) {
                        groupVolumes[group, default: 0] += weight
                    }
                }
            }
            
            // Aggregate sets by muscle group
            if let setsPerMuscle = stat.setsPerMuscle {
                for (muscle, sets) in setsPerMuscle {
                    if let group = MuscleGroup.fromMuscle(muscle) {
                        groupSets[group, default: 0] += sets
                    }
                }
            }
            
            // Aggregate reps by muscle group
            if let repsPerMuscle = stat.repsPerMuscle {
                for (muscle, reps) in repsPerMuscle {
                    if let group = MuscleGroup.fromMuscle(muscle) {
                        groupReps[group, default: 0] += reps
                    }
                }
            }
            
            return WeeklyMuscleGroupData(
                weekId: stat.id,
                date: date,
                groupVolumes: groupVolumes,
                groupSets: groupSets,
                groupReps: groupReps
            )
        }
        .sorted { $0.date < $1.date }
    }
    
    // MARK: - Get top muscles by volume
    static func getTopMuscles(from stats: WeeklyStats?, limit: Int = 5) -> [MuscleVolumeData] {
        guard let stats = stats,
              let weightPerMuscle = stats.weightPerMuscle else { return [] }
        
        var muscleData: [MuscleVolumeData] = []
        
        for (muscle, weight) in weightPerMuscle {
            let sets = stats.setsPerMuscle?[muscle] ?? 0
            let reps = stats.repsPerMuscle?[muscle] ?? 0
            
            muscleData.append(MuscleVolumeData(
                muscleName: muscle.capitalized,
                weight: weight,
                sets: sets,
                reps: reps
            ))
        }
        
        // Sort by weight and take top N
        return Array(muscleData.sorted { $0.weight > $1.weight }.prefix(limit))
    }
    
    // MARK: - Get undertrained muscles
    static func getUndertrainedMuscles(from stats: WeeklyStats?) -> [MuscleVolumeData] {
        guard let stats = stats else { return [] }
        
        var undertrainedMuscles: [MuscleVolumeData] = []
        
        // Get all muscles that were trained
        let allTrainedMuscles = Set(
            (stats.weightPerMuscle?.keys ?? []) +
            (stats.setsPerMuscle?.keys ?? []) +
            (stats.repsPerMuscle?.keys ?? [])
        )
        
        for muscle in allTrainedMuscles {
            let weight = stats.weightPerMuscle?[muscle] ?? 0
            let sets = stats.setsPerMuscle?[muscle] ?? 0
            let reps = stats.repsPerMuscle?[muscle] ?? 0
            
            // Check if undertrained
            if sets < UndertrainedThresholds.minSets || weight < UndertrainedThresholds.minWeight {
                undertrainedMuscles.append(MuscleVolumeData(
                    muscleName: muscle.capitalized,
                    weight: weight,
                    sets: sets,
                    reps: reps
                ))
            }
        }
        
        // Sort by sets (ascending) then weight (ascending)
        return undertrainedMuscles.sorted { 
            if $0.sets != $1.sets {
                return $0.sets < $1.sets
            }
            return $0.weight < $1.weight
        }
    }
    
    // MARK: - Format week label
    static func formatWeekLabel(_ weekId: String) -> String {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        
        guard let date = formatter.date(from: weekId) else { return weekId }
        
        let outputFormatter = DateFormatter()
        outputFormatter.dateFormat = "MMM d"
        return outputFormatter.string(from: date)
    }
} 