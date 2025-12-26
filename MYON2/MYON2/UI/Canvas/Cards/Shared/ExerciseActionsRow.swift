import SwiftUI

/// Action row for a single exercise: Swap menu, Info, Remove
/// Used in both SessionPlanCard and RoutineSummaryCard when exercise is expanded
public struct ExerciseActionsRow: View {
    let exercise: PlanExercise
    let onSwap: (SwapReason) -> Void
    let onInfo: () -> Void
    let onRemove: (() -> Void)?  // Optional - not always available
    
    public enum SwapReason: String, CaseIterable {
        case sameMuscles = "same_muscles"
        case sameEquipment = "same_equipment"
        case differentAngle = "different_angle"
        case aiSuggestion = "ai_suggestion"
        case manualSearch = "manual_search"
        
        var label: String {
            switch self {
            case .sameMuscles: return "Same muscle, different equipment"
            case .sameEquipment: return "Same equipment, different angle"
            case .differentAngle: return "Different movement pattern"
            case .aiSuggestion: return "Coach's pick"
            case .manualSearch: return "Search exercises..."
            }
        }
        
        var icon: String {
            switch self {
            case .sameMuscles: return "figure.strengthtraining.traditional"
            case .sameEquipment: return "dumbbell"
            case .differentAngle: return "arrow.triangle.branch"
            case .aiSuggestion: return "sparkles"
            case .manualSearch: return "magnifyingglass"
            }
        }
    }
    
    public var body: some View {
        HStack(spacing: Space.sm) {
            // Swap dropdown with AI options + manual search
            Menu {
                // AI swap options
                ForEach([SwapReason.sameMuscles, .sameEquipment, .differentAngle, .aiSuggestion], id: \.self) { reason in
                    Button {
                        onSwap(reason)
                    } label: {
                        Label(reason.label, systemImage: reason.icon)
                    }
                }
                
                Divider()
                
                // Manual search option
                Button {
                    onSwap(.manualSearch)
                } label: {
                    Label(SwapReason.manualSearch.label, systemImage: SwapReason.manualSearch.icon)
                }
            } label: {
                HStack(spacing: 4) {
                    Image(systemName: "arrow.left.arrow.right")
                        .font(.system(size: 11))
                    Text("Swap")
                        .font(.system(size: 12, weight: .medium))
                    Image(systemName: "chevron.down")
                        .font(.system(size: 8))
                }
                .foregroundColor(ColorsToken.Brand.primary)
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .background(ColorsToken.Brand.primary.opacity(0.1))
                .clipShape(Capsule())
            }
            
            // Exercise Info button
            Button(action: onInfo) {
                HStack(spacing: 4) {
                    Image(systemName: "info.circle")
                        .font(.system(size: 11))
                    Text("Info")
                        .font(.system(size: 12, weight: .medium))
                }
                .foregroundColor(ColorsToken.Text.secondary)
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .background(ColorsToken.Background.secondary)
                .clipShape(Capsule())
            }
            .buttonStyle(PlainButtonStyle())
            
            // Remove Exercise button (if available)
            if let remove = onRemove {
                Button(action: remove) {
                    HStack(spacing: 4) {
                        Image(systemName: "trash")
                            .font(.system(size: 11))
                        Text("Remove")
                            .font(.system(size: 12, weight: .medium))
                    }
                    .foregroundColor(ColorsToken.State.error.opacity(0.8))
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(ColorsToken.State.error.opacity(0.08))
                    .clipShape(Capsule())
                }
                .buttonStyle(PlainButtonStyle())
            }
            
            Spacer()
        }
        .padding(.horizontal, Space.md)
        .padding(.vertical, Space.xs)
    }
}

// MARK: - Swap Instruction Builder

extension ExerciseActionsRow {
    /// Builds the instruction string for AI swap based on reason and exercise context
    public static func buildSwapInstruction(
        exercise: PlanExercise,
        reason: SwapReason
    ) -> (instruction: String, visibleResponse: String) {
        let muscleDescription = deriveMuscleDescription(from: exercise)
        let equipmentDescription = deriveEquipmentDescription(from: exercise)
        
        switch reason {
        case .sameMuscles:
            return (
                "Swap \(exercise.name) for another exercise targeting \(muscleDescription) but with different equipment. Keep the same sets/reps prescription.",
                "Let me find another \(muscleDescription) exercise with different equipment..."
            )
        case .sameEquipment:
            return (
                "Swap \(exercise.name) for another \(equipmentDescription) exercise targeting a different angle or variation. Keep the same sets/reps prescription.",
                "Let me find another \(equipmentDescription) exercise with a different angle..."
            )
        case .differentAngle:
            return (
                "Swap \(exercise.name) for a different variation that targets \(muscleDescription) from a different angle or movement pattern.",
                "Let me find a different movement pattern for \(muscleDescription)..."
            )
        case .aiSuggestion:
            return (
                "Suggest the best replacement for \(exercise.name) that fits this workout's overall balance and the user's needs. Consider variety, muscle coverage, and available equipment.",
                "Let me pick the best alternative for \(exercise.name)..."
            )
        case .manualSearch:
            return (
                "",  // Not used for manual search
                ""
            )
        }
    }
    
    private static func deriveMuscleDescription(from exercise: PlanExercise) -> String {
        if let muscles = exercise.primaryMuscles, !muscles.isEmpty {
            return muscles.joined(separator: ", ")
        }
        
        // Derive from exercise name
        let nameLower = exercise.name.lowercased()
        if nameLower.contains("squat") || nameLower.contains("leg press") || nameLower.contains("lunge") {
            return "quadriceps, glutes"
        } else if nameLower.contains("deadlift") || nameLower.contains("hip thrust") {
            return "hamstrings, glutes"
        } else if nameLower.contains("bench") || nameLower.contains("chest") || nameLower.contains("fly") {
            return "chest"
        } else if nameLower.contains("row") || nameLower.contains("pull") || nameLower.contains("lat") {
            return "back, lats"
        } else if nameLower.contains("press") || nameLower.contains("shoulder") || nameLower.contains("delt") {
            return "shoulders"
        } else if nameLower.contains("curl") {
            return "biceps"
        } else if nameLower.contains("extension") || nameLower.contains("tricep") || nameLower.contains("pushdown") {
            return "triceps"
        }
        return "the same muscles"
    }
    
    private static func deriveEquipmentDescription(from exercise: PlanExercise) -> String {
        if let equip = exercise.equipment, !equip.isEmpty {
            return equip
        }
        
        // Derive from exercise name
        let nameLower = exercise.name.lowercased()
        if nameLower.contains("barbell") || nameLower.contains("bb ") {
            return "barbell"
        } else if nameLower.contains("dumbbell") || nameLower.contains("db ") {
            return "dumbbell"
        } else if nameLower.contains("cable") {
            return "cable"
        } else if nameLower.contains("machine") {
            return "machine"
        }
        return "similar equipment"
    }
}
