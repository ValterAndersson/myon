import SwiftUI

// MARK: - Set Cell Model (Render Model)

/// Unified render model for displaying a set row across all modes.
/// This is a pure UI adapter - it does not contain business logic.
/// Mode is NOT stored here; SetTable owns the mode.
struct SetCellModel: Identifiable, Equatable {
    typealias ID = String
    
    let id: ID
    
    /// Display label for set index (e.g., "1", "2", "W1" for warmup)
    let indexLabel: String
    
    // Display values (unitless - unit is rendered by SetTable header)
    let weight: String?    // e.g., "95" not "95kg"
    let reps: String?      // e.g., "8"
    let rir: String?       // e.g., "2" or nil for warmup
    
    /// Set type indicator for visual badge (W=warmup, F=failure, D=drop)
    let setTypeIndicator: SetTypeIndicator?
    
    // State
    let isActive: Bool
    let isCompleted: Bool
    
    // MARK: - Set Type Indicator
    
    enum SetTypeIndicator: Equatable {
        case warmup
        case failure
        case drop
        
        var label: String {
            switch self {
            case .warmup: return "W"
            case .failure: return "F"
            case .drop: return "D"
            }
        }
        
        var color: Color {
            switch self {
            case .warmup: return Color.warning
            case .failure: return Color.destructive
            case .drop: return Color.accent
            }
        }
    }
}

// MARK: - WorkoutExerciseSet Mapper

extension WorkoutExerciseSet {
    /// Maps a history/completed set to SetCellModel for read-only display.
    /// Index label is passed in to avoid requiring the model to know its position.
    func toSetCellModel(indexLabel: String) -> SetCellModel {
        let indicator = setTypeIndicator(from: type)
        
        return SetCellModel(
            id: id,
            indexLabel: indicator != nil ? indicator!.label : indexLabel,
            weight: formatWeight(weight),
            reps: "\(reps)",
            rir: rir > 0 ? "\(rir)" : nil,
            setTypeIndicator: indicator,
            isActive: false,
            isCompleted: isCompleted
        )
    }
    
    private func setTypeIndicator(from type: String) -> SetCellModel.SetTypeIndicator? {
        let lowercased = type.lowercased()
        if lowercased.contains("warm") {
            return .warmup
        } else if lowercased.contains("fail") || lowercased.contains("amrap") {
            return .failure
        } else if lowercased.contains("drop") {
            return .drop
        }
        return nil
    }
    
    private func formatWeight(_ weight: Double) -> String {
        // Unitless - SetTable will add unit in header
        if weight.truncatingRemainder(dividingBy: 1) == 0 {
            return "\(Int(weight))"
        }
        return String(format: "%.1f", weight)
    }
}

// MARK: - Array Helper for Building SetCellModels

extension Array where Element == WorkoutExerciseSet {
    /// Convert array of WorkoutExerciseSet to SetCellModels with proper index labels.
    /// Handles warmup vs working set numbering.
    func toSetCellModels() -> [SetCellModel] {
        var warmupIndex = 0
        var workingIndex = 0
        
        return self.map { set in
            let indexLabel: String
            let lowercased = set.type.lowercased()
            
            if lowercased.contains("warm") {
                warmupIndex += 1
                indexLabel = "W\(warmupIndex)"
            } else {
                workingIndex += 1
                indexLabel = "\(workingIndex)"
            }
            
            return set.toSetCellModel(indexLabel: indexLabel)
        }
    }
}
