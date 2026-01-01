import SwiftUI

/// Unified exercise row with expandable sets grid
/// Used by both SessionPlanCard and RoutineSummaryCard
public struct ExerciseRowView: View {
    let exerciseIndex: Int
    @Binding var exercises: [PlanExercise]
    @Binding var selectedCell: GridCellField?
    let isExpanded: Bool
    let isPlanningMode: Bool
    let showDivider: Bool
    
    // Callbacks
    let onToggleExpand: () -> Void
    let onSwap: (PlanExercise, ExerciseActionsRow.SwapReason) -> Void
    let onInfo: (PlanExercise) -> Void
    let onRemove: ((Int) -> Void)?  // Optional - not always available
    
    // Warmup collapse state (managed externally)
    @Binding var warmupCollapsed: Bool
    
    private var exercise: PlanExercise? {
        exercises[safe: exerciseIndex]
    }
    
    public var body: some View {
        if let exercise = exercise {
            VStack(spacing: 0) {
                // Header row - tappable to expand/collapse
                exerciseHeaderRow(exercise: exercise)
                
                // Expanded: show actions + SetGridView
                if isExpanded {
                    expandedContent(exercise: exercise)
                }
                
                // Divider
                if showDivider {
                    Rectangle()
                        .fill(ColorsToken.Border.subtle.opacity(0.5))
                        .frame(height: 1)
                        .padding(.leading, Space.md)
                }
            }
        }
    }
    
    // MARK: - Exercise Header Row
    
    private func exerciseHeaderRow(exercise: PlanExercise) -> some View {
        Button(action: onToggleExpand) {
            HStack(spacing: Space.sm) {
                // Exercise name and prescription
                VStack(alignment: .leading, spacing: 2) {
                    Text(exercise.name)
                        .font(.system(size: 15, weight: .medium))
                        .foregroundColor(ColorsToken.Text.primary)
                    
                    // Summary line
                    Text(exercise.summaryLine)
                        .font(.system(size: 13))
                        .foregroundColor(ColorsToken.Text.secondary)
                }
                
                Spacer()
                
                // Expand/collapse chevron
                Image(systemName: isExpanded ? "chevron.down" : "chevron.right")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(ColorsToken.Text.secondary.opacity(0.5))
            }
            .padding(.vertical, 12)
            .padding(.horizontal, Space.sm)
            .background(isExpanded ? ColorsToken.Background.secondary.opacity(0.5) : ColorsToken.Surface.card)
            .contentShape(Rectangle())
        }
        .buttonStyle(PlainButtonStyle())
    }
    
    // MARK: - Expanded Content
    
    private func expandedContent(exercise: PlanExercise) -> some View {
        VStack(spacing: 0) {
            // Actions row (Swap, Info, Remove)
            ExerciseActionsRow(
                exercise: exercise,
                onSwap: { reason in onSwap(exercise, reason) },
                onInfo: { onInfo(exercise) },
                onRemove: onRemove != nil ? { onRemove?(exerciseIndex) } : nil
            )
            
            // SetGridView for inline editing
            SetGridView(
                sets: Binding(
                    get: { exercises[safe: exerciseIndex]?.sets ?? [] },
                    set: { newSets in
                        if exercises.indices.contains(exerciseIndex) {
                            exercises[exerciseIndex].sets = newSets
                        }
                    }
                ),
                selectedCell: $selectedCell,
                exerciseName: exercise.name,
                warmupCollapsed: warmupCollapsed,
                isPlanningMode: isPlanningMode,
                onWarmupToggle: { warmupCollapsed.toggle() },
                onAddSet: { setType in
                    addSet(type: setType)
                },
                onDeleteSet: { setIdx in
                    deleteSet(at: setIdx)
                },
                onUndoDelete: nil  // TODO: Implement undo
            )
        }
        .background(ColorsToken.Background.secondary.opacity(0.3))
    }
    
    // MARK: - Set Operations
    
    private func addSet(type: SetType) {
        guard exercises.indices.contains(exerciseIndex) else { return }
        
        if let lastSet = exercises[exerciseIndex].sets.last {
            let newSet = PlanSet(
                type: type,
                reps: type == .warmup ? 10 : lastSet.reps,
                weight: lastSet.weight,
                rir: type == .warmup ? nil : lastSet.rir
            )
            exercises[exerciseIndex].sets.append(newSet)
        } else {
            let newSet = PlanSet(
                type: type,
                reps: type == .warmup ? 10 : 8,
                weight: nil,
                rir: type == .warmup ? nil : 2
            )
            exercises[exerciseIndex].sets.append(newSet)
        }
    }
    
    private func deleteSet(at setIndex: Int) {
        guard exercises.indices.contains(exerciseIndex),
              exercises[exerciseIndex].sets.indices.contains(setIndex) else { return }
        
        exercises[exerciseIndex].sets.remove(at: setIndex)
        selectedCell = nil
    }
}

// MARK: - Safe Array Access

private extension Array {
    subscript(safe index: Int) -> Element? {
        get { indices.contains(index) ? self[index] : nil }
        set {
            if let newValue = newValue, indices.contains(index) {
                self[index] = newValue
            }
        }
    }
}

// MARK: - Preview

#if DEBUG
struct ExerciseRowView_Previews: PreviewProvider {
    struct PreviewWrapper: View {
        @State private var exercises: [PlanExercise] = [
            PlanExercise(name: "Bench Press", sets: [
                PlanSet(type: .warmup, reps: 10, weight: 40, rir: nil),
                PlanSet(type: .working, reps: 8, weight: 80, rir: 2),
                PlanSet(type: .working, reps: 8, weight: 80, rir: 2),
                PlanSet(type: .working, reps: 8, weight: 80, rir: 1)
            ])
        ]
        @State private var selectedCell: GridCellField? = nil
        @State private var isExpanded = true
        @State private var warmupCollapsed = true
        
        var body: some View {
            ScrollView {
                VStack(spacing: 0) {
                    ExerciseRowView(
                        exerciseIndex: 0,
                        exercises: $exercises,
                        selectedCell: $selectedCell,
                        isExpanded: isExpanded,
                        isPlanningMode: true,
                        showDivider: false,
                        onToggleExpand: { isExpanded.toggle() },
                        onSwap: { ex, reason in print("Swap \(ex.name) - \(reason)") },
                        onInfo: { ex in print("Info for \(ex.name)") },
                        onRemove: { idx in print("Remove at \(idx)") },
                        warmupCollapsed: $warmupCollapsed
                    )
                }
                .padding()
            }
            .background(ColorsToken.Background.primary)
        }
    }
    
    static var previews: some View {
        PreviewWrapper()
    }
}
#endif
