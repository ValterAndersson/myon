/**
 * FocusModeComponents.swift
 *
 * Reusable UI components for Focus Mode workout execution.
 * These components are designed for the premium execution surface.
 */

import SwiftUI

// MARK: - Screen Mode State Machine

enum FocusModeScreenMode: Equatable {
    case normal
    case editingSet(exerciseId: String, setId: String)
    case reordering
    
    var isReordering: Bool {
        if case .reordering = self { return true }
        return false
    }
    
    var isEditing: Bool {
        if case .editingSet = self { return true }
        return false
    }
}

// MARK: - Active Sheet Enum

enum FocusModeActiveSheet: Identifiable, Equatable {
    case coach
    case exerciseSearch
    case startTimeEditor
    case setTypePicker(exerciseId: String, setId: String)
    case moreActions(exerciseId: String)
    
    var id: String {
        switch self {
        case .coach: return "coach"
        case .exerciseSearch: return "exerciseSearch"
        case .startTimeEditor: return "startTimeEditor"
        case .setTypePicker(let exId, let setId): return "setTypePicker-\(exId)-\(setId)"
        case .moreActions(let exId): return "moreActions-\(exId)"
        }
    }
}

// MARK: - Timer Pill

struct TimerPill: View {
    let elapsedTime: TimeInterval
    let completedSets: Int
    let totalSets: Int
    
    var body: some View {
        HStack(spacing: Space.xs) {
            Text(formatDuration(elapsedTime))
                .font(.system(size: 14, weight: .medium).monospacedDigit())
                .foregroundColor(ColorsToken.Text.primary)
            
            if totalSets > 0 {
                Text("·")
                    .foregroundColor(ColorsToken.Text.muted)
                
                Text("\(completedSets)/\(totalSets)")
                    .font(.system(size: 13, weight: .medium).monospacedDigit())
                    .foregroundColor(ColorsToken.Text.secondary)
            }
        }
        .padding(.horizontal, Space.md)
        .padding(.vertical, Space.sm)
        .background(ColorsToken.Background.secondary)
        .clipShape(Capsule())
        .frame(minWidth: 80) // Prevent jitter
    }
    
    private func formatDuration(_ interval: TimeInterval) -> String {
        let hours = Int(interval) / 3600
        let minutes = (Int(interval) % 3600) / 60
        let seconds = Int(interval) % 60
        
        if hours > 0 {
            return String(format: "%d:%02d:%02d", hours, minutes, seconds)
        }
        return String(format: "%02d:%02d", minutes, seconds)
    }
}

// MARK: - Coach Button (AI Copilot)

struct CoachButton: View {
    let action: () -> Void
    
    var body: some View {
        Button(action: action) {
            HStack(spacing: Space.xs) {
                Image(systemName: "sparkles")
                    .font(.system(size: 14, weight: .medium))
                Text("Coach")
                    .font(.system(size: 14, weight: .semibold))
            }
            .foregroundColor(.white)
            .padding(.horizontal, Space.md)
            .padding(.vertical, Space.sm)
            .background(ColorsToken.Brand.emeraldFill)
            .clipShape(Capsule())
        }
        .buttonStyle(PlainButtonStyle())
    }
}

// MARK: - Reorder Toggle Button

struct ReorderToggleButton: View {
    let isReordering: Bool
    let action: () -> Void
    
    var body: some View {
        Button(action: action) {
            Text(isReordering ? "Done" : "Reorder")
                .font(.system(size: 14, weight: .medium))
                .foregroundColor(isReordering ? ColorsToken.Brand.primary : ColorsToken.Text.secondary)
                .padding(.horizontal, Space.sm)
                .padding(.vertical, Space.xs)
        }
        .buttonStyle(PlainButtonStyle())
    }
}

// MARK: - Reorder Mode Banner

struct ReorderModeBanner: View {
    var body: some View {
        HStack {
            Image(systemName: "line.3.horizontal")
                .font(.system(size: 14, weight: .medium))
                .foregroundColor(ColorsToken.Text.secondary)
            
            Text("Reorder exercises")
                .font(.system(size: 13, weight: .medium))
                .foregroundColor(ColorsToken.Text.secondary)
            
            Spacer()
        }
        .padding(.horizontal, Space.lg)
        .padding(.vertical, Space.sm)
        .background(ColorsToken.Brand.accent100.opacity(0.5))
    }
}

// MARK: - Action Rail

enum ActionPriority: Int, Comparable {
    case coach = 0      // P0: Auto-fill, Recalibrate, Adjust next
    case utility = 1    // P1: Last time, +2.5kg
    case advanced = 2   // P2: Edit warm-ups, Convert to dropset
    
    static func < (lhs: ActionPriority, rhs: ActionPriority) -> Bool {
        lhs.rawValue < rhs.rawValue
    }
}

struct ActionItem: Identifiable {
    let id = UUID()
    let icon: String
    let label: String
    let priority: ActionPriority
    let isPrimary: Bool
    let action: () -> Void
}

struct ActionRail: View {
    let actions: [ActionItem]
    let isActive: Bool
    let onMoreTap: () -> Void
    
    private var visibleActions: [ActionItem] {
        let sorted = actions.sorted { $0.priority < $1.priority }
        if isActive {
            return Array(sorted.prefix(5))
        } else {
            return Array(sorted.prefix(2))
        }
    }
    
    private var hasMore: Bool {
        actions.count > (isActive ? 5 : 2)
    }
    
    var body: some View {
        VStack(alignment: .leading, spacing: Space.xs) {
            Text("Actions")
                .font(.system(size: 12, weight: .medium))
                .foregroundColor(ColorsToken.Text.muted)
                .padding(.leading, Space.md)
            
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: Space.sm) {
                    ForEach(visibleActions) { action in
                        ActionPill(
                            icon: action.icon,
                            label: action.label,
                            isPrimary: action.isPrimary,
                            action: action.action
                        )
                    }
                    
                    if hasMore {
                        ActionPill(
                            icon: "ellipsis",
                            label: "More",
                            isPrimary: false,
                            action: onMoreTap
                        )
                    }
                }
                .padding(.horizontal, Space.md)
            }
        }
        .padding(.bottom, Space.sm)
    }
}

struct ActionPill: View {
    let icon: String
    let label: String
    let isPrimary: Bool
    let action: () -> Void
    
    var body: some View {
        Button(action: action) {
            HStack(spacing: 4) {
                Image(systemName: icon)
                    .font(.system(size: 11, weight: .medium))
                Text(label)
                    .font(.system(size: 12, weight: .medium))
            }
            .foregroundColor(isPrimary ? .white : ColorsToken.Brand.primary)
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(isPrimary ? ColorsToken.Brand.emeraldFill : ColorsToken.Brand.primary.opacity(0.08))
            .clipShape(Capsule())
            .overlay(
                isPrimary ? nil : Capsule().stroke(ColorsToken.Brand.primary.opacity(0.2), lineWidth: StrokeWidthToken.hairline)
            )
        }
        .buttonStyle(PlainButtonStyle())
    }
}

// MARK: - Bottom CTA Section

struct WorkoutBottomCTA: View {
    let onFinish: () -> Void
    let onDiscard: () -> Void
    let safeAreaBottom: CGFloat
    
    var body: some View {
        VStack(spacing: Space.sm) {
            // Finish Workout - Primary CTA
            Button(action: onFinish) {
                Text("Finish Workout")
                    .font(.system(size: 17, weight: .semibold))
                    .foregroundColor(.white)
                    .frame(maxWidth: .infinity)
                    .frame(height: 56)
                    .background(ColorsToken.Brand.emeraldFill)
                    .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.medium))
            }
            .buttonStyle(PlainButtonStyle())
            
            // Discard Workout - Destructive secondary
            Button(action: onDiscard) {
                Text("Discard Workout")
                    .font(.system(size: 15, weight: .medium))
                    .foregroundColor(ColorsToken.State.error)
            }
            .buttonStyle(PlainButtonStyle())
            .padding(.top, Space.xs)
        }
        .padding(.horizontal, Space.md)
        .padding(.top, Space.lg)
        .padding(.bottom, safeAreaBottom + LayoutToken.bottomCTAExtraPadding)
    }
}

// MARK: - Exercise Card Container

struct ExerciseCardContainer<Content: View>: View {
    let isActive: Bool
    let content: () -> Content
    
    var body: some View {
        content()
            .background(ColorsToken.Surface.card)
            .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.card))
            .overlay(
                RoundedRectangle(cornerRadius: CornerRadiusToken.card)
                    .stroke(
                        isActive ? ColorsToken.Stroke.cardActive : ColorsToken.Stroke.card,
                        lineWidth: isActive ? 2 : StrokeWidthToken.hairline
                    )
            )
            .overlay(
                // Left emerald accent for active card
                isActive ?
                    HStack {
                        RoundedRectangle(cornerRadius: 2)
                            .fill(ColorsToken.Brand.primary)
                            .frame(width: 3)
                        Spacer()
                    }
                    .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.card))
                : nil
            )
    }
}

// MARK: - Dotted Warmup Divider

struct WarmupDivider: View {
    var body: some View {
        GeometryReader { geo in
            Path { path in
                path.move(to: CGPoint(x: 0, y: 0.5))
                path.addLine(to: CGPoint(x: geo.size.width, y: 0.5))
            }
            .stroke(
                ColorsToken.Separator.dottedWarmup,
                style: StrokeStyle(lineWidth: 1, dash: [3, 3])
            )
        }
        .frame(height: 1)
        .padding(.vertical, Space.sm)
    }
}

// MARK: - Compact Completion Circle

struct CompletionCircle: View {
    let isDone: Bool
    let action: () -> Void
    
    var body: some View {
        Button(action: action) {
            ZStack {
                Circle()
                    .stroke(
                        isDone ? ColorsToken.State.success.opacity(0.3) : ColorsToken.Text.secondary.opacity(0.2),
                        lineWidth: isDone ? 2 : 1.5
                    )
                    .frame(width: 20, height: 20)
                
                if isDone {
                    Image(systemName: "checkmark")
                        .font(.system(size: 10, weight: .bold))
                        .foregroundColor(ColorsToken.State.success)
                }
            }
            .frame(width: 44, height: 44) // 44pt hit target
            .contentShape(Rectangle())
        }
        .buttonStyle(PlainButtonStyle())
    }
}

// MARK: - Segmented Scope Control

struct ScopeSegmentedControl: View {
    @Binding var selectedScope: FocusModeEditScope
    let thisCount: Int
    let remainingCount: Int
    let allCount: Int
    
    var body: some View {
        HStack(spacing: 0) {
            scopeButton(.thisOnly, label: "This", count: nil)
            scopeButton(.remaining, label: "Remaining", count: remainingCount)
            scopeButton(.allWorking, label: "All", count: allCount)
        }
        .background(ColorsToken.Background.secondary)
        .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.small))
        .overlay(
            RoundedRectangle(cornerRadius: CornerRadiusToken.small)
                .stroke(ColorsToken.Border.subtle, lineWidth: StrokeWidthToken.hairline)
        )
    }
    
    private func scopeButton(_ scope: FocusModeEditScope, label: String, count: Int?) -> some View {
        let isSelected = selectedScope == scope
        
        return Button {
            withAnimation(.easeInOut(duration: 0.15)) {
                selectedScope = scope
            }
            UISelectionFeedbackGenerator().selectionChanged()
        } label: {
            HStack(spacing: 2) {
                Text(label)
                    .font(.system(size: 12, weight: isSelected ? .semibold : .regular))
                if let count = count {
                    Text("(\(count))")
                        .font(.system(size: 11, weight: .regular).monospacedDigit())
                }
            }
            .foregroundColor(isSelected ? .white : ColorsToken.Text.secondary)
            .padding(.horizontal, Space.sm)
            .padding(.vertical, 6)
            .background(isSelected ? ColorsToken.Brand.primary : Color.clear)
            .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.small - 2))
        }
        .buttonStyle(PlainButtonStyle())
    }
}

// MARK: - Reorder Row (Collapsed)

/// Compact exercise row for reorder mode.
/// Shows drag handle prominently with visual lift (shadow + scale).
struct ExerciseReorderRow: View {
    let exercise: FocusModeExercise
    
    /// Track if this row is being dragged (for visual feedback)
    @State private var isDragging = false
    
    var body: some View {
        HStack(spacing: Space.md) {
            // Drag handle - prominent and interactive
            Image(systemName: "line.3.horizontal")
                .font(.system(size: 18, weight: .semibold))
                .foregroundColor(ColorsToken.Brand.primary)
                .frame(width: 28, height: 28)
                .background(ColorsToken.Brand.primary.opacity(0.1))
                .clipShape(RoundedRectangle(cornerRadius: 6))
            
            VStack(alignment: .leading, spacing: 2) {
                Text(exercise.name)
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(ColorsToken.Text.primary)
                    .lineLimit(1)
                
                Text("\(exercise.completedSetsCount)/\(exercise.totalWorkingSetsCount) sets")
                    .font(.system(size: 13).monospacedDigit())
                    .foregroundColor(ColorsToken.Text.secondary)
            }
            
            Spacer()
            
            if exercise.isComplete {
                Image(systemName: "checkmark.circle.fill")
                    .foregroundColor(ColorsToken.State.success)
                    .font(.system(size: 18))
            }
        }
        .padding(.horizontal, Space.md)
        .padding(.vertical, Space.md)
        .background(ColorsToken.Surface.card)
        .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.card))
        .overlay(
            RoundedRectangle(cornerRadius: CornerRadiusToken.card)
                .stroke(ColorsToken.Stroke.card, lineWidth: StrokeWidthToken.hairline)
        )
        // Elevated appearance to signal "draggable"
        .shadow(color: Color.black.opacity(0.06), radius: 3, x: 0, y: 2)
        .contentShape(Rectangle())
    }
}

// MARK: - Preview

#Preview {
    VStack(spacing: Space.lg) {
        TimerPill(elapsedTime: 3661, completedSets: 6, totalSets: 18)
        
        HStack(spacing: Space.md) {
            CoachButton { }
            ReorderToggleButton(isReordering: false) { }
            ReorderToggleButton(isReordering: true) { }
        }
        
        ReorderModeBanner()
        
        WarmupDivider()
            .padding(.horizontal)
        
        HStack {
            CompletionCircle(isDone: false) { }
            CompletionCircle(isDone: true) { }
        }
        
        Spacer()
    }
    .padding()
    .background(ColorsToken.Background.screen)
}
