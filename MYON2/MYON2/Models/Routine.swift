import Foundation

struct Routine: Codable, Identifiable {
    let id: String
    let userId: String
    var name: String
    var description: String?
    var templateIds: [String] // References to WorkoutTemplate IDs
    var frequency: Int // How many workouts per week
    var createdAt: Date
    var updatedAt: Date
    
    // Cursor fields for deterministic next workout selection
    var lastCompletedTemplateId: String?
    var lastCompletedAt: Date?
    
    enum CodingKeys: String, CodingKey {
        case id
        case userId = "user_id"
        case name
        case description
        case templateIds = "template_ids"
        case frequency
        case createdAt = "created_at"
        case updatedAt = "updated_at"
        case lastCompletedTemplateId = "last_completed_template_id"
        case lastCompletedAt = "last_completed_at"
    }
}

// MARK: - Template Analytics (For Planning)
struct TemplateAnalytics: Codable, Equatable {
    let templateId: String
    let totalSets: Int
    let totalReps: Int
    let projectedVolume: Double // Based on planned weights
    let weightFormat: String
    let estimatedDuration: Int? // In minutes
    
    // Muscle stimulus projections
    let projectedVolumePerMuscleGroup: [String: Double]
    let projectedVolumePerMuscle: [String: Double]
    let setsPerMuscleGroup: [String: Int]
    let setsPerMuscle: [String: Int]
    let repsPerMuscleGroup: [String: Double]
    let repsPerMuscle: [String: Double]
    
    // Relative stimulus scores (normalized 0-100)
    let relativeStimulusPerMuscleGroup: [String: Double]
    let relativeStimulusPerMuscle: [String: Double]
    
    enum CodingKeys: String, CodingKey {
        case templateId = "template_id"
        case totalSets = "total_sets"
        case totalReps = "total_reps"
        case projectedVolume = "projected_volume"
        case weightFormat = "weight_format"
        case estimatedDuration = "estimated_duration"
        case projectedVolumePerMuscleGroup = "projected_volume_per_muscle_group"
        case projectedVolumePerMuscle = "projected_volume_per_muscle"
        case setsPerMuscleGroup = "sets_per_muscle_group"
        case setsPerMuscle = "sets_per_muscle"
        case repsPerMuscleGroup = "reps_per_muscle_group"
        case repsPerMuscle = "reps_per_muscle"
        case relativeStimulusPerMuscleGroup = "relative_stimulus_per_muscle_group"
        case relativeStimulusPerMuscle = "relative_stimulus_per_muscle"
    }
}

// MARK: - Routine Analytics (Weekly Projections)
struct RoutineAnalytics: Codable {
    let routineId: String
    let frequency: Int
    let totalWeeklySets: Int
    let totalWeeklyReps: Int
    let totalWeeklyVolume: Double
    let weightFormat: String
    let estimatedWeeklyDuration: Int // In minutes
    
    // Weekly muscle stimulus projections
    let weeklyVolumePerMuscleGroup: [String: Double]
    let weeklyVolumePerMuscle: [String: Double]
    let weeklySetsPerMuscleGroup: [String: Int]
    let weeklySetsPerMuscle: [String: Int]
    let weeklyRepsPerMuscleGroup: [String: Double]
    let weeklyRepsPerMuscle: [String: Double]
    
    // Balance analysis
    let muscleGroupBalance: MuscleGroupBalance
    let recommendations: [String]
    
    enum CodingKeys: String, CodingKey {
        case routineId = "routine_id"
        case frequency
        case totalWeeklySets = "total_weekly_sets"
        case totalWeeklyReps = "total_weekly_reps"
        case totalWeeklyVolume = "total_weekly_volume"
        case weightFormat = "weight_format"
        case estimatedWeeklyDuration = "estimated_weekly_duration"
        case weeklyVolumePerMuscleGroup = "weekly_volume_per_muscle_group"
        case weeklyVolumePerMuscle = "weekly_volume_per_muscle"
        case weeklySetsPerMuscleGroup = "weekly_sets_per_muscle_group"
        case weeklySetsPerMuscle = "weekly_sets_per_muscle"
        case weeklyRepsPerMuscleGroup = "weekly_reps_per_muscle_group"
        case weeklyRepsPerMuscle = "weekly_reps_per_muscle"
        case muscleGroupBalance = "muscle_group_balance"
        case recommendations
    }
}

// MARK: - Muscle Group Balance Analysis
struct MuscleGroupBalance: Codable {
    let pushPullRatio: Double // Push volume / Pull volume
    let upperLowerRatio: Double // Upper body / Lower body
    let anteriorPosteriorRatio: Double // Front chain / Back chain
    let leftRightBalance: Double // For unilateral exercises
    let balanceScore: Double // Overall balance score 0-100
    let imbalances: [MuscleImbalance]
    
    enum CodingKeys: String, CodingKey {
        case pushPullRatio = "push_pull_ratio"
        case upperLowerRatio = "upper_lower_ratio"
        case anteriorPosteriorRatio = "anterior_posterior_ratio"
        case leftRightBalance = "left_right_balance"
        case balanceScore = "balance_score"
        case imbalances
    }
}

struct MuscleImbalance: Codable {
    let type: String // "push_pull", "upper_lower", etc.
    let severity: String // "minor", "moderate", "major"
    let description: String
    let recommendation: String
}

// MARK: - Stimulus Calculation Helper
struct StimulusCalculator {
    
    static func calculateTemplateAnalytics(
        template: WorkoutTemplate,
        exercises: [Exercise],
        weightFormat: String = "kg"
    ) -> TemplateAnalytics {
        
        var totalSets = 0
        var totalReps = 0
        var projectedVolume = 0.0
        var projectedVolumePerMuscleGroup: [String: Double] = [:]
        var projectedVolumePerMuscle: [String: Double] = [:]
        var setsPerMuscleGroup: [String: Int] = [:]
        var setsPerMuscle: [String: Int] = [:]
        var repsPerMuscleGroup: [String: Double] = [:]
        var repsPerMuscle: [String: Double] = [:]
        
        for templateExercise in template.exercises {
            guard let exercise = exercises.first(where: { $0.id == templateExercise.exerciseId }) else {
                continue
            }
            
            let workingSets = templateExercise.sets.filter { isWorkingSet($0.type) }
            let exerciseSets = workingSets.count
            let exerciseReps = workingSets.reduce(0) { $0 + $1.reps }
            let exerciseVolume = workingSets.reduce(0) { $0 + ($1.weight * Double($1.reps)) }
            
            totalSets += exerciseSets
            totalReps += exerciseReps
            projectedVolume += exerciseVolume
            
            // Distribute across muscle groups using categories
            for category in exercise.muscleCategories {
                setsPerMuscleGroup[category, default: 0] += exerciseSets
                let categoryVolume = exerciseVolume / Double(exercise.muscleCategories.count)
                let categoryReps = Double(exerciseReps) / Double(exercise.muscleCategories.count)
                projectedVolumePerMuscleGroup[category, default: 0] += categoryVolume
                repsPerMuscleGroup[category, default: 0] += categoryReps
            }
            
            // Distribute across individual muscles using contributions
            for (muscle, contribution) in exercise.muscleContributions {
                setsPerMuscle[muscle, default: 0] += exerciseSets
                projectedVolumePerMuscle[muscle, default: 0] += exerciseVolume * contribution
                repsPerMuscle[muscle, default: 0] += Double(exerciseReps) * contribution
            }
        }
        
        // Calculate relative stimulus (normalized scores)
        let maxMuscleGroupVolume = projectedVolumePerMuscleGroup.values.max() ?? 1.0
        let maxMuscleVolume = projectedVolumePerMuscle.values.max() ?? 1.0
        
        let relativeStimulusPerMuscleGroup = projectedVolumePerMuscleGroup.mapValues {
            ($0 / maxMuscleGroupVolume) * 100
        }
        let relativeStimulusPerMuscle = projectedVolumePerMuscle.mapValues {
            ($0 / maxMuscleVolume) * 100
        }
        
        return TemplateAnalytics(
            templateId: template.id,
            totalSets: totalSets,
            totalReps: totalReps,
            projectedVolume: projectedVolume,
            weightFormat: weightFormat,
            estimatedDuration: nil, // Will be calculated by AI later
            projectedVolumePerMuscleGroup: projectedVolumePerMuscleGroup,
            projectedVolumePerMuscle: projectedVolumePerMuscle,
            setsPerMuscleGroup: setsPerMuscleGroup,
            setsPerMuscle: setsPerMuscle,
            repsPerMuscleGroup: repsPerMuscleGroup,
            repsPerMuscle: repsPerMuscle,
            relativeStimulusPerMuscleGroup: relativeStimulusPerMuscleGroup,
            relativeStimulusPerMuscle: relativeStimulusPerMuscle
        )
    }
    
    static func calculateRoutineAnalytics(
        routine: Routine,
        templateAnalytics: [TemplateAnalytics]
    ) -> RoutineAnalytics {
        
        let weightFormat = templateAnalytics.first?.weightFormat ?? "kg"
        
        // Aggregate weekly totals
        let totalWeeklySets = templateAnalytics.reduce(0) { $0 + $1.totalSets }
        let totalWeeklyReps = templateAnalytics.reduce(0) { $0 + $1.totalReps }
        let totalWeeklyVolume = templateAnalytics.reduce(0) { $0 + $1.projectedVolume }
        let estimatedWeeklyDuration = templateAnalytics.compactMap(\.estimatedDuration).reduce(0, +)
        
        // Aggregate muscle group metrics
        var weeklyVolumePerMuscleGroup: [String: Double] = [:]
        var weeklySetsPerMuscleGroup: [String: Int] = [:]
        var weeklyRepsPerMuscleGroup: [String: Double] = [:]
        
        var weeklyVolumePerMuscle: [String: Double] = [:]
        var weeklySetsPerMuscle: [String: Int] = [:]
        var weeklyRepsPerMuscle: [String: Double] = [:]
        
        for analytics in templateAnalytics {
            // Muscle groups
            for (group, volume) in analytics.projectedVolumePerMuscleGroup {
                weeklyVolumePerMuscleGroup[group, default: 0] += volume
            }
            for (group, sets) in analytics.setsPerMuscleGroup {
                weeklySetsPerMuscleGroup[group, default: 0] += sets
            }
            for (group, reps) in analytics.repsPerMuscleGroup {
                weeklyRepsPerMuscleGroup[group, default: 0] += reps
            }
            
            // Individual muscles
            for (muscle, volume) in analytics.projectedVolumePerMuscle {
                weeklyVolumePerMuscle[muscle, default: 0] += volume
            }
            for (muscle, sets) in analytics.setsPerMuscle {
                weeklySetsPerMuscle[muscle, default: 0] += sets
            }
            for (muscle, reps) in analytics.repsPerMuscle {
                weeklyRepsPerMuscle[muscle, default: 0] += reps
            }
        }
        
        // Calculate balance analysis
        let muscleGroupBalance = calculateMuscleGroupBalance(
            weeklyVolumePerMuscleGroup: weeklyVolumePerMuscleGroup,
            weeklySetsPerMuscleGroup: weeklySetsPerMuscleGroup
        )
        
        // Generate recommendations
        let recommendations = generateRecommendations(
            balance: muscleGroupBalance,
            weeklyVolume: weeklyVolumePerMuscleGroup,
            frequency: routine.frequency
        )
        
        return RoutineAnalytics(
            routineId: routine.id,
            frequency: routine.frequency,
            totalWeeklySets: totalWeeklySets,
            totalWeeklyReps: totalWeeklyReps,
            totalWeeklyVolume: totalWeeklyVolume,
            weightFormat: weightFormat,
            estimatedWeeklyDuration: estimatedWeeklyDuration,
            weeklyVolumePerMuscleGroup: weeklyVolumePerMuscleGroup,
            weeklyVolumePerMuscle: weeklyVolumePerMuscle,
            weeklySetsPerMuscleGroup: weeklySetsPerMuscleGroup,
            weeklySetsPerMuscle: weeklySetsPerMuscle,
            weeklyRepsPerMuscleGroup: weeklyRepsPerMuscleGroup,
            weeklyRepsPerMuscle: weeklyRepsPerMuscle,
            muscleGroupBalance: muscleGroupBalance,
            recommendations: recommendations
        )
    }
    
    private static func isWorkingSet(_ type: String) -> Bool {
        let workingSetTypes = ["working set", "drop set", "failure set"]
        return workingSetTypes.contains(type.lowercased())
    }
    
    private static func calculateMuscleGroupBalance(
        weeklyVolumePerMuscleGroup: [String: Double],
        weeklySetsPerMuscleGroup: [String: Int]
    ) -> MuscleGroupBalance {
        
        // Define muscle group mappings
        let pushGroups = ["chest", "shoulders", "triceps"]
        let pullGroups = ["back", "biceps"]
        let upperGroups = ["chest", "back", "shoulders", "triceps", "biceps"]
        let lowerGroups = ["glutes", "quadriceps", "hamstrings", "calves"]
        
        let pushVolume = pushGroups.compactMap { weeklyVolumePerMuscleGroup[$0] }.reduce(0, +)
        let pullVolume = pullGroups.compactMap { weeklyVolumePerMuscleGroup[$0] }.reduce(0, +)
        let upperVolume = upperGroups.compactMap { weeklyVolumePerMuscleGroup[$0] }.reduce(0, +)
        let lowerVolume = lowerGroups.compactMap { weeklyVolumePerMuscleGroup[$0] }.reduce(0, +)
        
        let pushPullRatio = pullVolume > 0 ? pushVolume / pullVolume : 0
        let upperLowerRatio = lowerVolume > 0 ? upperVolume / lowerVolume : 0
        
        // Calculate balance score (closer to ideal ratios = higher score)
        let idealPushPull = 1.0 // 1:1 ratio
        let idealUpperLower = 1.0 // 1:1 ratio
        
        let pushPullScore = max(0, 100 - abs(pushPullRatio - idealPushPull) * 50)
        let upperLowerScore = max(0, 100 - abs(upperLowerRatio - idealUpperLower) * 50)
        let balanceScore = (pushPullScore + upperLowerScore) / 2
        
        // Identify imbalances
        var imbalances: [MuscleImbalance] = []
        
        if abs(pushPullRatio - idealPushPull) > 0.3 {
            let severity = abs(pushPullRatio - idealPushPull) > 0.6 ? "major" : "moderate"
            let issueMuscle = pushPullRatio > idealPushPull ? "pull" : "push"
            imbalances.append(MuscleImbalance(
                type: "push_pull",
                severity: severity,
                description: "Push/pull ratio is \(String(format: "%.1f", pushPullRatio)):1",
                recommendation: "Add more \(issueMuscle) exercises to balance the routine"
            ))
        }
        
        return MuscleGroupBalance(
            pushPullRatio: pushPullRatio,
            upperLowerRatio: upperLowerRatio,
            anteriorPosteriorRatio: 1.0, // Placeholder
            leftRightBalance: 1.0, // Placeholder
            balanceScore: balanceScore,
            imbalances: imbalances
        )
    }
    
    private static func generateRecommendations(
        balance: MuscleGroupBalance,
        weeklyVolume: [String: Double],
        frequency: Int
    ) -> [String] {
        var recommendations: [String] = []
        
        // Balance recommendations
        for imbalance in balance.imbalances {
            recommendations.append(imbalance.recommendation)
        }
        
        // Volume recommendations
        let totalVolume = weeklyVolume.values.reduce(0, +)
        if totalVolume < 5000 {
            recommendations.append("Consider increasing overall training volume for better results")
        }
        
        // Frequency recommendations
        if frequency < 3 {
            recommendations.append("Training 3+ times per week typically yields better results")
        }
        
        return recommendations
    }
}
