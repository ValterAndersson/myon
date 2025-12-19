import SwiftUI

// MARK: - Cell Selection (uses set ID for stable identity)

enum GridCellField: Equatable, Hashable {
    case weight(setId: String)
    case reps(setId: String)
    case rir(setId: String)
    case done(setId: String)
    
    var setId: String {
        switch self {
        case .weight(let id), .reps(let id), .rir(let id), .done(let id):
            return id
        }
    }
    
    var fieldType: String {
        switch self {
        case .weight: return "weight"
        case .reps: return "reps"
        case .rir: return "rir"
        case .done: return "done"
        }
    }
}

// MARK: - Edit Scope

enum EditScope: String, CaseIterable {
    case allWorking = "All Working"
    case remaining = "Remaining"
    case thisOnly = "This Only"
}

// MARK: - Set Grid View

/// A spreadsheet-style grid for displaying and editing sets.
/// Follows the gym-safe design: large tap targets, selection + dock editing, bulk scope.
struct SetGridView: View {
    @Binding var sets: [PlanSet]
    @Binding var selectedCell: GridCellField?
    let exerciseName: String
    let warmupCollapsed: Bool
    let isPlanningMode: Bool  // Hide Done column in planning mode
    let onWarmupToggle: () -> Void
    let onAddSet: (SetType) -> Void
    let onDeleteSet: (Int) -> Void
    let onUndoDelete: (() -> Void)?  // For undo toast
    
    @State private var editScope: EditScope = .allWorking
    @State private var deletedSet: (index: Int, set: PlanSet)? = nil
    @State private var showUndoToast: Bool = false
    
    // Computed
    private var warmupSets: [(index: Int, set: PlanSet)] {
        sets.enumerated().filter { $0.element.isWarmup }.map { ($0.offset, $0.element) }
    }
    
    private var workingSets: [(index: Int, set: PlanSet)] {
        sets.enumerated().filter { !$0.element.isWarmup }.map { ($0.offset, $0.element) }
    }
    
    // State for set type picker
    @State private var setTypePickerSetId: String? = nil
    
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Grid header
            gridHeader
            
            // All sets in one unified grid (warmups + working together)
            ForEach(Array(sets.enumerated()), id: \.element.id) { index, set in
                VStack(spacing: 0) {
                    SetGridRow(
                        setNumber: displayNumber(for: index),
                        set: set,
                        actualIndex: index,
                        isWarmup: set.isWarmup,
                        isPlanningMode: isPlanningMode,
                        selectedCell: $selectedCell,
                        onSetNumberTap: { setTypePickerSetId = set.id },
                        onDelete: { onDeleteSet(index) }
                    )
                    
                    // Inline editor - appears directly under selected row
                    if selectedCell?.setId == set.id {
                        InlineEditingDock(
                            selectedCell: selectedCell!,
                            sets: $sets,
                            editScope: $editScope,
                            onDismiss: { selectedCell = nil }
                        )
                    }
                }
                
                if index < sets.count - 1 {
                    Divider()
                        .padding(.leading, 44)
                }
            }
            
            // Add set button
            addSetButton
        }
        .sheet(isPresented: Binding(
            get: { setTypePickerSetId != nil },
            set: { if !$0 { setTypePickerSetId = nil } }
        )) {
            if let setId = setTypePickerSetId,
               let index = sets.firstIndex(where: { $0.id == setId }) {
                SetTypePickerSheet(
                    currentType: sets[index].type ?? .working,
                    onSelect: { newType in
                        sets[index].type = newType
                        setTypePickerSetId = nil
                    },
                    onDismiss: { setTypePickerSetId = nil }
                )
            }
        }
    }
    
    /// Display number for row - warmups show "W1", "W2", working shows "1", "2", etc.
    private func displayNumber(for index: Int) -> String {
        let set = sets[index]
        if set.isWarmup {
            let warmupIndex = sets.prefix(index + 1).filter { $0.isWarmup }.count
            return "W\(warmupIndex)"
        } else {
            let workingIndex = sets.prefix(index + 1).filter { !$0.isWarmup }.count
            return "\(workingIndex)"
        }
    }
    
    
    // MARK: - Grid Header
    
    private var gridHeader: some View {
        HStack(spacing: 0) {
            Text("Set")
                .frame(width: 44, alignment: .leading)
            
            Text("Weight")
                .frame(width: 72, alignment: .trailing)  // Right-align for tabular
            
            Text("Reps")
                .frame(width: 56, alignment: .trailing)  // Right-align for tabular
            
            Text("RIR")
                .frame(width: 48, alignment: .center)
            
            Spacer()
            
            // Hide Done column in planning mode
            if !isPlanningMode {
                Text("Done")
                    .frame(width: 48, alignment: .center)
            }
        }
        .font(.system(size: 11, weight: .bold))  // Bolder for better hierarchy
        .foregroundColor(ColorsToken.Text.secondary.opacity(0.8))  // Darker
        .textCase(.uppercase)
        .padding(.horizontal, Space.md)
        .padding(.vertical, 10)  // Slightly taller
        .background(ColorsToken.Background.secondary.opacity(0.5))  // Darker background
    }
    
    // MARK: - Add Set Button
    
    private var addSetButton: some View {
        Menu {
            Button {
                onAddSet(.warmup)
            } label: {
                Label("Add Warm-up", systemImage: "flame")
            }
            
            Button {
                onAddSet(.working)
            } label: {
                Label("Add Working Set", systemImage: "plus.circle")
            }
        } label: {
            HStack(spacing: 6) {
                Image(systemName: "plus")
                    .font(.system(size: 13, weight: .medium))
                Text("Add Set")
                    .font(.system(size: 13, weight: .medium))
            }
            .foregroundColor(ColorsToken.Brand.primary)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 12)
        }
        .buttonStyle(PlainButtonStyle())
    }
}

// MARK: - Set Grid Row

private struct SetGridRow: View {
    let setNumber: String  // Now accepts formatted string like "W1", "1", etc.
    let set: PlanSet
    let actualIndex: Int
    let isWarmup: Bool
    let isPlanningMode: Bool
    @Binding var selectedCell: GridCellField?
    var onSetNumberTap: (() -> Void)? = nil  // Opens type picker
    let onDelete: () -> Void
    
    // Row height - compact but still tappable
    private let rowHeight: CGFloat = 48
    
    // Check if set has custom values (not linked to base)
    private var hasOverride: Bool {
        !isWarmup && !set.isLinkedToBase
    }
    
    // Check if this row is selected (any cell)
    private var isRowSelected: Bool {
        guard let selected = selectedCell else { return false }
        return selected.setId == set.id
    }
    
    /// Set type badge text (W for warmup, F for failure, D for dropset)
    private var setTypeBadge: String? {
        guard let setType = set.type else { return nil }
        switch setType {
        case .warmup: return nil  // Already shown in number
        case .failureSet: return "F"
        case .dropSet: return "D"
        case .working: return nil
        }
    }
    
    var body: some View {
        HStack(spacing: 0) {
            // Set number - tappable to change type
            Button(action: { onSetNumberTap?() }) {
                HStack(spacing: 4) {
                    Text(setNumber)
                        .font(.system(size: 14, weight: .semibold).monospacedDigit())
                        .foregroundColor(isWarmup ? ColorsToken.Text.secondary : ColorsToken.Text.primary)
                    
                    // Type badge for special sets
                    if let badge = setTypeBadge {
                        Text(badge)
                            .font(.system(size: 10, weight: .bold))
                            .foregroundColor(.white)
                            .frame(width: 16, height: 16)
                            .background(set.type == .failureSet ? ColorsToken.State.error : ColorsToken.State.warning)
                            .clipShape(Circle())
                    }
                    
                    // Override indicator (small dot)
                    if hasOverride && setTypeBadge == nil {
                        Circle()
                            .fill(ColorsToken.State.warning)
                            .frame(width: 6, height: 6)
                    }
                }
            }
            .buttonStyle(PlainButtonStyle())
            .frame(width: 44, alignment: .leading)
            
            // Weight cell (right-aligned for tabular data)
            GridCell(
                value: set.weight.map { formatWeight($0) } ?? "—",
                isSelected: selectedCell == .weight(setId: set.id),
                isSecondary: isWarmup,
                alignment: .trailing,
                onTap: { selectedCell = .weight(setId: set.id) }
            )
            .frame(width: 72)
            
            // Reps cell (right-aligned)
            GridCell(
                value: "\(set.reps)",
                isSelected: selectedCell == .reps(setId: set.id),
                isSecondary: isWarmup,
                alignment: .trailing,
                onTap: { selectedCell = .reps(setId: set.id) }
            )
            .frame(width: 56)
            
            // RIR cell (right-aligned)
            GridCell(
                value: isWarmup ? "—" : (set.rir.map { "\($0)" } ?? "—"),
                isSelected: selectedCell == .rir(setId: set.id),
                isSecondary: isWarmup || set.rir == nil,
                alignment: .center,
                onTap: {
                    if !isWarmup {
                        selectedCell = .rir(setId: set.id)
                    }
                }
            )
            .frame(width: 48)
            
            Spacer()
            
            // Done checkbox (hidden in planning mode)
            if !isPlanningMode {
                Button {
                    selectedCell = .done(setId: set.id)
                } label: {
                    Image(systemName: set.isCompleted == true ? "checkmark.circle.fill" : "circle")
                        .font(.system(size: 22))
                        .foregroundColor(set.isCompleted == true ? ColorsToken.State.success : ColorsToken.Text.secondary.opacity(0.4))
                }
                .buttonStyle(PlainButtonStyle())
                .frame(width: 48, height: 48)
            }
        }
        .frame(height: rowHeight)
        .padding(.horizontal, Space.md)
        .background(rowBackground)
        .swipeActions(edge: .trailing, allowsFullSwipe: true) {
            Button(role: .destructive) {
                onDelete()
            } label: {
                Label("Delete", systemImage: "trash")
            }
        }
    }
    
    private var rowBackground: Color {
        if isRowSelected {
            return ColorsToken.Brand.primary.opacity(0.08)
        } else if isWarmup {
            return ColorsToken.Background.secondary.opacity(0.3)
        } else {
            return ColorsToken.Surface.card
        }
    }
    
    private func formatWeight(_ w: Double) -> String {
        if w.truncatingRemainder(dividingBy: 1) == 0 {
            return "\(Int(w))kg"
        } else {
            return String(format: "%.1fkg", w)
        }
    }
}

// MARK: - Grid Cell

private struct GridCell: View {
    let value: String
    let isSelected: Bool
    let isSecondary: Bool
    var alignment: Alignment = .center
    let onTap: () -> Void  // Handles both select and toggle
    
    // Minimum tap target per HIG
    private let minTapTarget: CGFloat = 40
    
    var body: some View {
        Button(action: onTap) {
            Text(value)
                .font(.system(size: 14, weight: isSelected ? .semibold : .regular).monospacedDigit())
                .foregroundColor(textColor)
                .frame(maxWidth: .infinity, minHeight: minTapTarget, alignment: alignment)
                .padding(.horizontal, 2)
                .background(
                    RoundedRectangle(cornerRadius: 4)
                        .fill(isSelected ? ColorsToken.Brand.primary.opacity(0.12) : Color.clear)
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 4)
                        .stroke(isSelected ? ColorsToken.Brand.primary : Color.clear, lineWidth: 1.5)
                )
        }
        .buttonStyle(PlainButtonStyle())
    }
    
    private var textColor: Color {
        if isSelected {
            return ColorsToken.Brand.primary
        } else if isSecondary || value == "—" {
            return ColorsToken.Text.secondary
        } else {
            return ColorsToken.Text.primary
        }
    }
}

// MARK: - Editing Dock

/// Bottom bar for inline editing. Appears when a cell is selected.
struct EditingDock: View {
    let selectedCell: GridCellField
    @Binding var sets: [PlanSet]
    @Binding var editScope: EditScope
    let onDismiss: () -> Void
    
    @State private var pendingValue: Double = 0
    
    var body: some View {
        VStack(spacing: 0) {
            Divider()
            
            VStack(spacing: Space.sm) {
                // Scope selector (only for working sets)
                if !isWarmupSet {
                    scopeSelector
                }
                
                // Value editor based on field type
                valueEditor
            }
            .padding(.horizontal, Space.md)
            .padding(.vertical, Space.sm)
            .background(ColorsToken.Brand.primary.opacity(0.08))  // Match selected row tint
        }
        .onAppear {
            loadCurrentValue()
        }
        .onChange(of: selectedCell) { _ in
            loadCurrentValue()
        }
    }
    
    // MARK: - Computed (find set by ID, not index)
    
    private var currentSetIndex: Int? {
        sets.firstIndex { $0.id == selectedCell.setId }
    }
    
    private var currentSet: PlanSet? {
        guard let idx = currentSetIndex else { return nil }
        return sets[safe: idx]
    }
    
    private var isWarmupSet: Bool {
        currentSet?.isWarmup ?? false
    }
    
    // MARK: - Scope Selector
    
    private var scopeSelector: some View {
        HStack(spacing: Space.xs) {
            ForEach(EditScope.allCases, id: \.rawValue) { scope in
                Button {
                    editScope = scope
                } label: {
                    Text(scope.rawValue)
                        .font(.system(size: 12, weight: editScope == scope ? .semibold : .regular))
                        .foregroundColor(editScope == scope ? .white : ColorsToken.Text.secondary)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 6)
                        .background(
                            editScope == scope
                                ? ColorsToken.Brand.primary
                                : ColorsToken.Background.secondary
                        )
                        .clipShape(Capsule())
                }
                .buttonStyle(PlainButtonStyle())
            }
            
            Spacer()
        }
    }
    
    // MARK: - Value Editor
    
    @ViewBuilder
    private var valueEditor: some View {
        switch selectedCell {
        case .weight:
            weightEditor
        case .reps:
            repsEditor
        case .rir:
            rirEditor
        case .done:
            doneEditor
        }
    }
    
    private var weightEditor: some View {
        HStack(spacing: Space.lg) {
            // Minus button
            Button {
                updateValue(pendingValue - 2.5)
            } label: {
                Image(systemName: "minus")
                    .font(.system(size: 20, weight: .semibold))
                    .foregroundColor(pendingValue <= 0 ? ColorsToken.Text.secondary.opacity(0.3) : ColorsToken.Brand.primary)
                    .frame(width: 56, height: 56)
                    .background(ColorsToken.Background.secondary)
                    .clipShape(Circle())
            }
            .disabled(pendingValue <= 0)
            
            // Value display - show decimal for .5 values
            VStack(spacing: 2) {
                Text(pendingValue > 0 ? formatWeightDisplay(pendingValue) : "—")
                    .font(.system(size: 28, weight: .bold).monospacedDigit())
                    .foregroundColor(ColorsToken.Text.primary)
                Text("kg")
                    .font(.system(size: 13))
                    .foregroundColor(ColorsToken.Text.secondary)
            }
            .frame(width: 80)
            
            // Plus button
            Button {
                updateValue(pendingValue + 2.5)
            } label: {
                Image(systemName: "plus")
                    .font(.system(size: 20, weight: .semibold))
                    .foregroundColor(ColorsToken.Brand.primary)
                    .frame(width: 56, height: 56)
                    .background(ColorsToken.Background.secondary)
                    .clipShape(Circle())
            }
            
            Spacer()
        }
        .buttonStyle(PlainButtonStyle())
    }
    
    private func formatWeightDisplay(_ w: Double) -> String {
        if w.truncatingRemainder(dividingBy: 1) == 0 {
            return "\(Int(w))"
        } else {
            return String(format: "%.1f", w)
        }
    }
    
    private var repsEditor: some View {
        HStack(spacing: Space.lg) {
            // Minus button
            Button {
                updateValue(pendingValue - 1)
            } label: {
                Image(systemName: "minus")
                    .font(.system(size: 20, weight: .semibold))
                    .foregroundColor(pendingValue <= 1 ? ColorsToken.Text.secondary.opacity(0.3) : ColorsToken.Brand.primary)
                    .frame(width: 56, height: 56)
                    .background(ColorsToken.Background.secondary)
                    .clipShape(Circle())
            }
            .disabled(pendingValue <= 1)
            
            // Value display
            VStack(spacing: 2) {
                Text("\(Int(pendingValue))")
                    .font(.system(size: 28, weight: .bold).monospacedDigit())
                    .foregroundColor(ColorsToken.Text.primary)
                Text("reps")
                    .font(.system(size: 13))
                    .foregroundColor(ColorsToken.Text.secondary)
            }
            .frame(width: 80)
            
            // Plus button
            Button {
                updateValue(pendingValue + 1)
            } label: {
                Image(systemName: "plus")
                    .font(.system(size: 20, weight: .semibold))
                    .foregroundColor(pendingValue >= 30 ? ColorsToken.Text.secondary.opacity(0.3) : ColorsToken.Brand.primary)
                    .frame(width: 56, height: 56)
                    .background(ColorsToken.Background.secondary)
                    .clipShape(Circle())
            }
            .disabled(pendingValue >= 30)
            
            Spacer()
        }
        .buttonStyle(PlainButtonStyle())
    }
    
    private var rirEditor: some View {
        VStack(alignment: .leading, spacing: Space.sm) {
            Text("RIR (Reps in Reserve)")
                .font(.system(size: 12, weight: .medium))
                .foregroundColor(ColorsToken.Text.secondary)
            
            HStack(spacing: Space.sm) {
                ForEach(0...5, id: \.self) { rir in
                    Button {
                        updateValue(Double(rir))
                    } label: {
                        Text("\(rir)")
                            .font(.system(size: 16, weight: .semibold))
                            .foregroundColor(Int(pendingValue) == rir ? .white : ColorsToken.Text.primary)
                            .frame(width: 48, height: 48)
                            .background(Int(pendingValue) == rir ? rirColor(rir) : ColorsToken.Background.secondary)
                            .clipShape(Circle())
                    }
                    .buttonStyle(PlainButtonStyle())
                }
                
                Spacer()
            }
        }
    }
    
    private var doneEditor: some View {
        HStack(spacing: Space.md) {
            Button {
                toggleDone()
                onDismiss()
            } label: {
                HStack {
                    Image(systemName: currentSet?.isCompleted == true ? "checkmark.circle.fill" : "circle")
                    Text(currentSet?.isCompleted == true ? "Mark Incomplete" : "Mark Complete")
                }
                .font(.system(size: 15, weight: .medium))
                .foregroundColor(currentSet?.isCompleted == true ? ColorsToken.Text.secondary : ColorsToken.State.success)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 14)
                .background(
                    currentSet?.isCompleted == true
                        ? ColorsToken.Background.secondary
                        : ColorsToken.State.success.opacity(0.12)
                )
                .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.medium))
            }
            .buttonStyle(PlainButtonStyle())
        }
    }
    
    // MARK: - Helpers
    
    private func loadCurrentValue() {
        guard let set = currentSet else { return }
        switch selectedCell {
        case .weight:
            pendingValue = set.weight ?? 0
        case .reps:
            pendingValue = Double(set.reps)
        case .rir:
            pendingValue = Double(set.rir ?? 2)
        case .done:
            break
        }
    }
    
    private func updateValue(_ newValue: Double) {
        pendingValue = newValue
        applyValueWithScope()
    }
    
    private func applyValueWithScope() {
        guard let currentIdx = currentSetIndex else { return }
        
        let indicesToUpdate: [Int]
        
        switch editScope {
        case .allWorking:
            // All working sets
            indicesToUpdate = sets.indices.filter { !sets[$0].isWarmup }
        case .remaining:
            // Current + all following working sets
            indicesToUpdate = sets.indices.filter { idx in
                !sets[idx].isWarmup && idx >= currentIdx
            }
        case .thisOnly:
            // Only this set
            indicesToUpdate = [currentIdx]
        }
        
        for idx in indicesToUpdate {
            switch selectedCell {
            case .weight:
                sets[idx].weight = pendingValue > 0 ? pendingValue : nil
                // Mark as override when value differs from first working set
                if editScope == .thisOnly {
                    sets[idx].isLinkedToBase = false
                }
            case .reps:
                sets[idx].reps = max(1, Int(pendingValue))
                if editScope == .thisOnly {
                    sets[idx].isLinkedToBase = false
                }
            case .rir:
                if !sets[idx].isWarmup {
                    sets[idx].rir = Int(pendingValue)
                    if editScope == .thisOnly {
                        sets[idx].isLinkedToBase = false
                    }
                }
            case .done:
                break
            }
        }
    }
    
    private func toggleDone() {
        guard let idx = currentSetIndex else { return }
        sets[idx].isCompleted = !(sets[idx].isCompleted ?? false)
    }
    
    private func rirColor(_ rir: Int) -> Color {
        switch rir {
        case 0: return ColorsToken.State.error
        case 1: return ColorsToken.State.warning
        case 2: return ColorsToken.Brand.primary
        default: return ColorsToken.Text.secondary
        }
    }
}

// MARK: - Inline Editing Dock (compact, appears directly under row)

private struct InlineEditingDock: View {
    let selectedCell: GridCellField
    @Binding var sets: [PlanSet]
    @Binding var editScope: EditScope
    let onDismiss: () -> Void
    
    @State private var pendingValue: Double = 0
    
    var body: some View {
        HStack(alignment: .top, spacing: Space.sm) {
            VStack(alignment: .leading, spacing: Space.xs) {
                // Scope selector (only for working sets)
                if !isWarmupSet {
                    compactScopeSelector
                }
                
                // Value editor based on field type
                compactValueEditor
            }
            
            Spacer()
            
            // Close button
            Button(action: onDismiss) {
                Image(systemName: "xmark")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundColor(ColorsToken.Text.secondary)
                    .frame(width: 28, height: 28)
                    .background(ColorsToken.Background.secondary)
                    .clipShape(Circle())
            }
            .buttonStyle(PlainButtonStyle())
        }
        .padding(.horizontal, Space.md)
        .padding(.vertical, Space.sm)
        .background(ColorsToken.Brand.primary.opacity(0.06))
        .onAppear {
            loadCurrentValue()
        }
        .onChange(of: selectedCell) { _ in
            loadCurrentValue()
        }
    }
    
    // MARK: - Computed
    
    private var currentSetIndex: Int? {
        sets.firstIndex { $0.id == selectedCell.setId }
    }
    
    private var currentSet: PlanSet? {
        guard let idx = currentSetIndex else { return nil }
        return sets[safe: idx]
    }
    
    private var isWarmupSet: Bool {
        currentSet?.isWarmup ?? false
    }
    
    // MARK: - Compact Scope Selector
    
    private var compactScopeSelector: some View {
        HStack(spacing: Space.xs) {
            ForEach(EditScope.allCases, id: \.rawValue) { scope in
                Button {
                    editScope = scope
                } label: {
                    Text(scope.rawValue)
                        .font(.system(size: 12, weight: editScope == scope ? .semibold : .regular))
                        .foregroundColor(editScope == scope ? .white : ColorsToken.Text.secondary)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 6)
                        .background(
                            editScope == scope
                                ? ColorsToken.Brand.primary
                                : ColorsToken.Background.secondary
                        )
                        .clipShape(Capsule())
                }
                .buttonStyle(PlainButtonStyle())
            }
            
            Spacer()
        }
    }
    
    // MARK: - Compact Value Editor
    
    @ViewBuilder
    private var compactValueEditor: some View {
        switch selectedCell {
        case .weight:
            compactWeightEditor
        case .reps:
            compactRepsEditor
        case .rir:
            compactRirEditor
        case .done:
            compactDoneEditor
        }
    }
    
    private var compactWeightEditor: some View {
        HStack(spacing: Space.md) {
            Button {
                updateValue(pendingValue - 2.5)
            } label: {
                Image(systemName: "minus")
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundColor(pendingValue <= 0 ? ColorsToken.Text.secondary.opacity(0.3) : ColorsToken.Brand.primary)
                    .frame(width: 48, height: 48)
                    .background(ColorsToken.Background.secondary)
                    .clipShape(Circle())
            }
            .disabled(pendingValue <= 0)
            
            VStack(spacing: 0) {
                Text(pendingValue > 0 ? formatWeight(pendingValue) : "—")
                    .font(.system(size: 24, weight: .bold).monospacedDigit())
                    .foregroundColor(ColorsToken.Text.primary)
                Text("kg")
                    .font(.system(size: 11))
                    .foregroundColor(ColorsToken.Text.secondary)
            }
            .frame(width: 70)
            
            Button {
                updateValue(pendingValue + 2.5)
            } label: {
                Image(systemName: "plus")
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundColor(ColorsToken.Brand.primary)
                    .frame(width: 48, height: 48)
                    .background(ColorsToken.Background.secondary)
                    .clipShape(Circle())
            }
            
            Spacer()
        }
        .buttonStyle(PlainButtonStyle())
    }
    
    private var compactRepsEditor: some View {
        HStack(spacing: Space.md) {
            Button {
                updateValue(pendingValue - 1)
            } label: {
                Image(systemName: "minus")
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundColor(pendingValue <= 1 ? ColorsToken.Text.secondary.opacity(0.3) : ColorsToken.Brand.primary)
                    .frame(width: 48, height: 48)
                    .background(ColorsToken.Background.secondary)
                    .clipShape(Circle())
            }
            .disabled(pendingValue <= 1)
            
            VStack(spacing: 0) {
                Text("\(Int(pendingValue))")
                    .font(.system(size: 24, weight: .bold).monospacedDigit())
                    .foregroundColor(ColorsToken.Text.primary)
                Text("reps")
                    .font(.system(size: 11))
                    .foregroundColor(ColorsToken.Text.secondary)
            }
            .frame(width: 70)
            
            Button {
                updateValue(pendingValue + 1)
            } label: {
                Image(systemName: "plus")
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundColor(pendingValue >= 30 ? ColorsToken.Text.secondary.opacity(0.3) : ColorsToken.Brand.primary)
                    .frame(width: 48, height: 48)
                    .background(ColorsToken.Background.secondary)
                    .clipShape(Circle())
            }
            .disabled(pendingValue >= 30)
            
            Spacer()
        }
        .buttonStyle(PlainButtonStyle())
    }
    
    private var compactRirEditor: some View {
        HStack(spacing: Space.sm) {
            ForEach(0...5, id: \.self) { rir in
                Button {
                    updateValue(Double(rir))
                } label: {
                    Text("\(rir)")
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundColor(Int(pendingValue) == rir ? .white : ColorsToken.Text.primary)
                        .frame(width: 40, height: 40)
                        .background(Int(pendingValue) == rir ? rirColor(rir) : ColorsToken.Background.secondary)
                        .clipShape(Circle())
                }
                .buttonStyle(PlainButtonStyle())
            }
            
            Spacer()
        }
    }
    
    private var compactDoneEditor: some View {
        Button {
            toggleDone()
            onDismiss()
        } label: {
            HStack {
                Image(systemName: currentSet?.isCompleted == true ? "checkmark.circle.fill" : "circle")
                Text(currentSet?.isCompleted == true ? "Mark Incomplete" : "Mark Complete")
            }
            .font(.system(size: 14, weight: .medium))
            .foregroundColor(currentSet?.isCompleted == true ? ColorsToken.Text.secondary : ColorsToken.State.success)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 12)
            .background(
                currentSet?.isCompleted == true
                    ? ColorsToken.Background.secondary
                    : ColorsToken.State.success.opacity(0.12)
            )
            .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.medium))
        }
        .buttonStyle(PlainButtonStyle())
    }
    
    // MARK: - Helpers
    
    private func loadCurrentValue() {
        guard let set = currentSet else { return }
        switch selectedCell {
        case .weight:
            pendingValue = set.weight ?? 0
        case .reps:
            pendingValue = Double(set.reps)
        case .rir:
            pendingValue = Double(set.rir ?? 2)
        case .done:
            break
        }
    }
    
    private func formatWeight(_ w: Double) -> String {
        if w.truncatingRemainder(dividingBy: 1) == 0 {
            return "\(Int(w))"
        } else {
            return String(format: "%.1f", w)
        }
    }
    
    private func updateValue(_ newValue: Double) {
        pendingValue = newValue
        applyValueWithScope()
    }
    
    private func applyValueWithScope() {
        guard let currentIdx = currentSetIndex else { return }
        
        let indicesToUpdate: [Int]
        
        switch editScope {
        case .allWorking:
            indicesToUpdate = sets.indices.filter { !sets[$0].isWarmup }
        case .remaining:
            indicesToUpdate = sets.indices.filter { idx in
                !sets[idx].isWarmup && idx >= currentIdx
            }
        case .thisOnly:
            indicesToUpdate = [currentIdx]
        }
        
        for idx in indicesToUpdate {
            switch selectedCell {
            case .weight:
                sets[idx].weight = pendingValue > 0 ? pendingValue : nil
                if editScope == .thisOnly {
                    sets[idx].isLinkedToBase = false
                }
            case .reps:
                sets[idx].reps = max(1, Int(pendingValue))
                if editScope == .thisOnly {
                    sets[idx].isLinkedToBase = false
                }
            case .rir:
                if !sets[idx].isWarmup {
                    sets[idx].rir = Int(pendingValue)
                    if editScope == .thisOnly {
                        sets[idx].isLinkedToBase = false
                    }
                }
            case .done:
                break
            }
        }
    }
    
    private func toggleDone() {
        guard let idx = currentSetIndex else { return }
        sets[idx].isCompleted = !(sets[idx].isCompleted ?? false)
    }
    
    private func rirColor(_ rir: Int) -> Color {
        switch rir {
        case 0: return ColorsToken.State.error
        case 1: return ColorsToken.State.warning
        case 2: return ColorsToken.Brand.primary
        default: return ColorsToken.Text.secondary
        }
    }
}

// MARK: - Set Type Picker Sheet

private struct SetTypePickerSheet: View {
    let currentType: SetType
    let onSelect: (SetType) -> Void
    let onDismiss: () -> Void
    
    var body: some View {
        NavigationView {
            VStack(alignment: .leading, spacing: 0) {
                Text("Set Type")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(ColorsToken.Text.secondary)
                    .padding(.horizontal, Space.lg)
                    .padding(.top, Space.lg)
                    .padding(.bottom, Space.sm)
                
                VStack(spacing: 0) {
                    setTypeOption(
                        type: .warmup,
                        title: "Warm-up",
                        description: "Lighter weight to prepare muscles. Doesn't count towards volume.",
                        icon: "flame",
                        color: ColorsToken.Text.secondary
                    )
                    
                    Divider().padding(.leading, 56)
                    
                    setTypeOption(
                        type: .working,
                        title: "Working Set",
                        description: "Standard working set that counts towards your volume.",
                        icon: "dumbbell",
                        color: ColorsToken.Brand.primary
                    )
                    
                    Divider().padding(.leading, 56)
                    
                    setTypeOption(
                        type: .failureSet,
                        title: "Failure",
                        description: "Push to muscular failure. Higher stimulus, more fatigue.",
                        icon: "flame.fill",
                        color: ColorsToken.State.error
                    )
                    
                    Divider().padding(.leading, 56)
                    
                    setTypeOption(
                        type: .dropSet,
                        title: "Drop Set",
                        description: "Immediately reduce weight and continue without rest.",
                        icon: "arrow.down.circle",
                        color: ColorsToken.State.warning
                    )
                }
                .background(ColorsToken.Surface.card)
                
                Spacer()
            }
            .background(ColorsToken.Background.primary)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Done") { onDismiss() }
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundColor(ColorsToken.Brand.primary)
                }
            }
        }
        .presentationDetents([.medium])
        .presentationDragIndicator(.visible)
    }
    
    private func setTypeOption(type: SetType, title: String, description: String, icon: String, color: Color) -> some View {
        Button {
            onSelect(type)
        } label: {
            HStack(spacing: Space.md) {
                Image(systemName: icon)
                    .font(.system(size: 18))
                    .foregroundColor(color)
                    .frame(width: 32)
                
                VStack(alignment: .leading, spacing: 2) {
                    Text(title)
                        .font(.system(size: 15, weight: .medium))
                        .foregroundColor(ColorsToken.Text.primary)
                    Text(description)
                        .font(.system(size: 12))
                        .foregroundColor(ColorsToken.Text.secondary)
                        .lineLimit(2)
                }
                
                Spacer()
                
                if currentType == type {
                    Image(systemName: "checkmark")
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundColor(ColorsToken.Brand.primary)
                }
            }
            .padding(.horizontal, Space.lg)
            .padding(.vertical, 14)
        }
        .buttonStyle(PlainButtonStyle())
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
