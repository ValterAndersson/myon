import SwiftUI

// MARK: - Muscle Group Definitions
enum MuscleGroup: String, CaseIterable {
    case chest = "Chest"
    case back = "Back"
    case arms = "Arms"
    case legs = "Legs"
    case shoulders = "Shoulders"
    
    // Fixed color palette for consistency across charts
    var color: Color {
        switch self {
        case .chest: return Color.red
        case .back: return Color.blue
        case .legs: return Color.green
        case .arms: return Color.orange
        case .shoulders: return Color.purple
        }
    }
    
    // Map individual muscles to their groups
    var muscles: [String] {
        switch self {
        case .chest:
            return ["pectoralis major", "pectoralis minor"]
        case .back:
            return ["latissimus dorsi", "rhomboids", "trapezius", "erector spinae", "teres major", "infraspinatus"]
        case .arms:
            return ["biceps brachii", "triceps brachii", "brachialis", "forearms", "anconeus"]
        case .legs:
            return ["quadriceps", "hamstrings", "gluteus maximus", "gluteus medius", "gluteus minimus", "gastrocnemius", "soleus", "adductors", "abductors", "calves"]
        case .shoulders:
            return ["anterior deltoid", "lateral deltoid", "posterior deltoid", "rotator cuff"]
        }
    }
    
    // Helper to get muscle group from muscle name
    static func fromMuscle(_ muscleName: String) -> MuscleGroup? {
        let normalized = muscleName.lowercased()
        for group in MuscleGroup.allCases {
            if group.muscles.contains(where: { $0.lowercased() == normalized }) {
                return group
            }
        }
        return nil
    }
}

// MARK: - Data Models for Dashboard
struct WeeklyMuscleGroupData {
    let weekId: String
    let date: Date
    let groupVolumes: [MuscleGroup: Double] // Total weight per group
    let groupSets: [MuscleGroup: Int]
    let groupReps: [MuscleGroup: Int]
}

struct MuscleVolumeData: Identifiable {
    let id = UUID()
    let muscleName: String
    let weight: Double
    let sets: Int
    let reps: Int
    var group: MuscleGroup? {
        MuscleGroup.fromMuscle(muscleName)
    }
} 