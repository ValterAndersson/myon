/**
 * FocusModeSetGrid.swift
 * 
 * Full-width spreadsheet-style set grid for Focus Mode.
 * 
 * Key design decisions:
 * - Always expanded (no collapsed state)
 * - Uses full available width with proportional columns
 * - Inline editing dock appears below selected row
 * - Swipe actions for delete/duplicate
 * - Large tap targets for fast input during workout
 */

import SwiftUI

// MARK: - Edit Scope (Apply to All/Remaining/This)

enum FocusModeEditScope: String, CaseIterable {
    case allWorking = "All Working"
    case remaining = "Remaining"
    case thisOnly = "This Only"
}

struct FocusModeSetGrid: View {
    let exercise: FocusModeExercise
    @Binding var selectedCell: FocusModeGridCell?
    
    let onLogSet: (String, String, Double?, Int, Int?) -> Void
    let onPatchField: (String, String, String, Any) -> Void
    let onAddSet: () -> Void
    let onRemoveSet: (String) -> Void
    
    // Row height - larger than typical for gym use (big fingers, sweat)
    private let rowHeight: CGFloat = 52
    
    // Set type picker state
    @State private var setTypePickerSetId: String? = nil
    
    var body: some View {
        VStack(spacing: 0) {
            // Header row
            gridHeader
            
            // Set rows - always visible, no collapse
            ForEach(Array(exercise.sets.enumerated()), id: \.element.id) { index, set in
                VStack(spacing: 0) {
                    setRow(set: set, index: index)
                        .contentShape(Rectangle())
                    
                    // Inline editing dock
                    if let selected = selectedCell,
                       selected.exerciseId == exercise.instanceId,
                       selected.setId == set.id {
                        FocusModeEditingDock(
                            selectedCell: selected,
                            set: set,
                            exerciseId: exercise.instanceId,
                            onValueChange: { field, value in
                                onPatchField(exercise.instanceId, set.id, field, value)
                            },
                            onLogSet: {
                                let weight = set.displayWeight
                                let reps = set.displayReps ?? 10
                                let rir = set.displayRir
                                onLogSet(exercise.instanceId, set.id, weight, reps, rir)
                                selectedCell = nil
                            },
                            onDismiss: {
                                withAnimation(.easeOut(duration: 0.15)) {
                                    selectedCell = nil
                                }
                            }
                        )
                        .transition(.opacity.combined(with: .move(edge: .top)))
                    }
                    
                    Divider()
                        .padding(.leading, Space.md)
                }
                .background(rowBackground(for: set))
                .swipeActions(edge: .trailing, allowsFullSwipe: true) {
                    Button(role: .destructive) {
                        onRemoveSet(set.id)
                    } label: {
                        Label("Delete", systemImage: "trash")
                    }
                }
            }
            
            // Add set button
            addSetButton
        }
        .sheet(isPresented: Binding(
            get: { setTypePickerSetId != nil },
            set: { if !$0 { setTypePickerSetId = nil } }
        )) {
            if let setId = setTypePickerSetId {
                FocusModeSetTypePickerSheet(
                    setId: setId,
                    exerciseId: exercise.instanceId,
                    currentType: exercise.sets.first { $0.id == setId }?.setType ?? .working,
                    isFailure: exercise.sets.first { $0.id == setId }?.tags?.isFailure ?? false,
                    onSelectType: { newType in
                        onPatchField(exercise.instanceId, setId, "set_type", newType.rawValue)
                        setTypePickerSetId = nil
                    },
                    onToggleFailure: { isFailure in
                        onPatchField(exercise.instanceId, setId, "is_failure", isFailure)
                        setTypePickerSetId = nil
                    },
                    onDismiss: { setTypePickerSetId = nil }
                )
            }
        }
    }
    
    // MARK: - Grid Header
    
    private var gridHeader: some View {
        GeometryReader { geo in
            let widths = columnWidths(for: geo.size.width)
            
            HStack(spacing: 0) {
                Text("SET")
                    .frame(width: widths.set, alignment: .leading)
                Text("WEIGHT")
                    .frame(width: widths.weight, alignment: .center)
                Text("REPS")
                    .frame(width: widths.reps, alignment: .center)
                Text("RIR")
                    .frame(width: widths.rir, alignment: .center)
                Text("✓")
                    .frame(width: widths.done, alignment: .center)
            }
            .font(.system(size: 11, weight: .semibold))
            .foregroundColor(ColorsToken.Text.secondary)
            .frame(height: 32)
            .padding(.horizontal, Space.md)
        }
        .frame(height: 32)
        .background(ColorsToken.Background.secondary.opacity(0.5))
    }
    
    // MARK: - Set Row
    
    private func setRow(set: FocusModeSet, index: Int) -> some View {
        GeometryReader { geo in
            let widths = columnWidths(for: geo.size.width)
            
            HStack(spacing: 0) {
                // SET column
                setNumberCell(set: set, index: index, width: widths.set)
                
                // WEIGHT column
                valueCell(
                    value: formatWeight(set.displayWeight),
                    isSelected: selectedCell == .weight(exerciseId: exercise.instanceId, setId: set.id),
                    isSecondary: set.isWarmup,
                    isDone: set.isDone,
                    width: widths.weight
                ) {
                    withAnimation(.easeInOut(duration: 0.15)) {
                        selectedCell = .weight(exerciseId: exercise.instanceId, setId: set.id)
                    }
                }
                
                // REPS column
                valueCell(
                    value: set.displayReps.map { "\($0)" } ?? "—",
                    isSelected: selectedCell == .reps(exerciseId: exercise.instanceId, setId: set.id),
                    isSecondary: set.isWarmup,
                    isDone: set.isDone,
                    width: widths.reps
                ) {
                    withAnimation(.easeInOut(duration: 0.15)) {
                        selectedCell = .reps(exerciseId: exercise.instanceId, setId: set.id)
                    }
                }
                
                // RIR column
                valueCell(
                    value: set.isWarmup ? "—" : (set.displayRir.map { "\($0)" } ?? "—"),
                    isSelected: selectedCell == .rir(exerciseId: exercise.instanceId, setId: set.id),
                    isSecondary: set.isWarmup || set.displayRir == nil,
                    isDone: set.isDone,
                    width: widths.rir
                ) {
                    if !set.isWarmup {
                        withAnimation(.easeInOut(duration: 0.15)) {
                            selectedCell = .rir(exerciseId: exercise.instanceId, setId: set.id)
                        }
                    }
                }
                
                // DONE column
                doneCell(set: set, width: widths.done)
            }
            .frame(height: rowHeight)
            .padding(.horizontal, Space.md)
        }
        .frame(height: rowHeight)
    }
    
    // MARK: - Column Cells
    
    private func setNumberCell(set: FocusModeSet, index: Int, width: CGFloat) -> some View {
        Button {
            setTypePickerSetId = set.id
        } label: {
            HStack(spacing: 4) {
                Text(displayNumber(for: index, set: set))
                    .font(.system(size: 15, weight: .semibold).monospacedDigit())
                    .foregroundColor(set.isWarmup ? ColorsToken.Text.secondary : ColorsToken.Text.primary)
                
                // Set type badge
                if let badge = setTypeBadge(for: set) {
                    Text(badge)
                        .font(.system(size: 10, weight: .bold))
                        .foregroundColor(.white)
                        .frame(width: 18, height: 18)
                        .background(set.tags?.isFailure == true ? ColorsToken.State.error : ColorsToken.State.warning)
                        .clipShape(Circle())
                }
            }
            .frame(width: width, alignment: .leading)
        }
        .buttonStyle(PlainButtonStyle())
    }
    
    private func valueCell(
        value: String,
        isSelected: Bool,
        isSecondary: Bool,
        isDone: Bool,
        width: CGFloat,
        onTap: @escaping () -> Void
    ) -> some View {
        Button(action: onTap) {
            Text(value)
                .font(.system(size: 16, weight: isSelected ? .semibold : .regular).monospacedDigit())
                .foregroundColor(cellTextColor(isSelected: isSelected, isSecondary: isSecondary, isDone: isDone, value: value))
                .frame(width: width - 8, height: rowHeight - 12)
                .background(
                    RoundedRectangle(cornerRadius: 6)
                        .fill(isSelected ? ColorsToken.Brand.primary.opacity(0.12) : Color.clear)
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 6)
                        .stroke(isSelected ? ColorsToken.Brand.primary : Color.clear, lineWidth: 2)
                )
        }
        .buttonStyle(PlainButtonStyle())
        .frame(width: width)
    }
    
    private func doneCell(set: FocusModeSet, width: CGFloat) -> some View {
        Button {
            if set.isDone {
                // Already done - tap to undo
                onPatchField(exercise.instanceId, set.id, "status", "planned")
            } else {
                // Mark as done with current values
                let weight = set.displayWeight
                let reps = set.displayReps ?? 10
                let rir = set.displayRir
                onLogSet(exercise.instanceId, set.id, weight, reps, rir)
            }
        } label: {
            Image(systemName: set.isDone ? "checkmark.circle.fill" : "circle")
                .font(.system(size: 26))
                .foregroundColor(set.isDone ? ColorsToken.State.success : ColorsToken.Text.secondary.opacity(0.3))
                .frame(width: width, height: rowHeight)
        }
        .buttonStyle(PlainButtonStyle())
    }
    
    // MARK: - Add Set Button
    
    private var addSetButton: some View {
        Button(action: onAddSet) {
            HStack(spacing: 6) {
                Image(systemName: "plus")
                    .font(.system(size: 14, weight: .medium))
                Text("Add Set")
                    .font(.system(size: 14, weight: .medium))
            }
            .foregroundColor(ColorsToken.Brand.primary)
            .frame(maxWidth: .infinity)
            .frame(height: 48)
        }
        .buttonStyle(PlainButtonStyle())
    }
    
    // MARK: - Helpers
    
    private struct ColumnWidths {
        let set: CGFloat
        let weight: CGFloat
        let reps: CGFloat
        let rir: CGFloat
        let done: CGFloat
    }
    
    private func columnWidths(for totalWidth: CGFloat) -> ColumnWidths {
        // Proportional widths optimized for workout logging
        // SET 12%, WEIGHT 30%, REPS 20%, RIR 18%, DONE 20%
        return ColumnWidths(
            set: totalWidth * 0.12,
            weight: totalWidth * 0.30,
            reps: totalWidth * 0.20,
            rir: totalWidth * 0.18,
            done: totalWidth * 0.20
        )
    }
    
    private func displayNumber(for index: Int, set: FocusModeSet) -> String {
        if set.isWarmup {
            let warmupIndex = exercise.sets.prefix(index + 1).filter { $0.isWarmup }.count
            return "W\(warmupIndex)"
        } else {
            let workingIndex = exercise.sets.prefix(index + 1).filter { !$0.isWarmup }.count
            return "\(workingIndex)"
        }
    }
    
    private func setTypeBadge(for set: FocusModeSet) -> String? {
        if set.tags?.isFailure == true { return "F" }
        if set.setType == .dropset { return "D" }
        return nil
    }
    
    private func formatWeight(_ weight: Double?) -> String {
        guard let w = weight else { return "—" }
        if w.truncatingRemainder(dividingBy: 1) == 0 {
            return "\(Int(w))"
        }
        return String(format: "%.1f", w)
    }
    
    private func cellTextColor(isSelected: Bool, isSecondary: Bool, isDone: Bool, value: String) -> Color {
        if isSelected { return ColorsToken.Brand.primary }
        if isDone { return ColorsToken.State.success }
        if isSecondary || value == "—" { return ColorsToken.Text.secondary }
        return ColorsToken.Text.primary
    }
    
    private func rowBackground(for set: FocusModeSet) -> Color {
        if let selected = selectedCell,
           selected.exerciseId == exercise.instanceId,
           selected.setId == set.id {
            return ColorsToken.Surface.focusedRow
        }
        if set.isDone {
            return ColorsToken.State.success.opacity(0.05)
        }
        if set.isWarmup {
            return ColorsToken.Background.secondary.opacity(0.3)
        }
        return Color.clear
    }
}

// MARK: - Editing Dock

struct FocusModeEditingDock: View {
    let selectedCell: FocusModeGridCell
    let set: FocusModeSet
    let exerciseId: String
    
    let onValueChange: (String, Any) -> Void
    let onLogSet: () -> Void
    let onDismiss: () -> Void
    
    @State private var isEditingText = false
    @State private var textInputValue = ""
    @FocusState private var textFieldFocused: Bool
    
    var body: some View {
        VStack(spacing: Space.sm) {
            HStack(alignment: .center, spacing: Space.md) {
                valueEditor
                
                Spacer()
                
                // Quick done button
                if !set.isDone {
                    Button(action: onLogSet) {
                        HStack(spacing: 4) {
                            Image(systemName: "checkmark")
                                .font(.system(size: 12, weight: .bold))
                            Text("Done")
                                .font(.system(size: 13, weight: .semibold))
                        }
                        .foregroundColor(.white)
                        .padding(.horizontal, 14)
                        .padding(.vertical, 8)
                        .background(ColorsToken.State.success)
                        .clipShape(Capsule())
                    }
                    .buttonStyle(PlainButtonStyle())
                }
                
                // Dismiss button
                Button(action: onDismiss) {
                    Image(systemName: "xmark")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundColor(ColorsToken.Text.secondary)
                        .frame(width: 32, height: 32)
                        .background(ColorsToken.Background.secondary)
                        .clipShape(Circle())
                }
                .buttonStyle(PlainButtonStyle())
            }
        }
        .padding(.horizontal, Space.md)
        .padding(.vertical, Space.sm)
        .background(ColorsToken.Neutral.n100.opacity(0.95))
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
            EmptyView()
        }
    }
    
    private var weightEditor: some View {
        HStack(spacing: Space.md) {
            stepButton(systemName: "minus", disabled: (set.displayWeight ?? 0) <= 0) {
                let newValue = (set.displayWeight ?? 0) - 2.5
                onValueChange("weight", max(0, newValue))
            }
            
            // Tappable value → TextField for direct keyboard input
            if isEditingText {
                VStack(spacing: 0) {
                    TextField("", text: $textInputValue)
                        .font(.system(size: 24, weight: .bold).monospacedDigit())
                        .keyboardType(.decimalPad)
                        .multilineTextAlignment(.center)
                        .focused($textFieldFocused)
                        .frame(width: 80)
                        .onSubmit { commitTextInput() }
                        .onChange(of: textFieldFocused) { _, focused in
                            if !focused { commitTextInput() }
                        }
                    Text("kg")
                        .font(.system(size: 11))
                        .foregroundColor(ColorsToken.Text.secondary)
                }
                .frame(width: 90)
            } else {
                Button {
                    let weight = set.displayWeight ?? 0
                    textInputValue = weight > 0 ? formatWeight(weight) : ""
                    isEditingText = true
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
                        textFieldFocused = true
                    }
                } label: {
                    VStack(spacing: 0) {
                        Text(formatWeight(set.displayWeight))
                            .font(.system(size: 28, weight: .bold).monospacedDigit())
                            .foregroundColor(ColorsToken.Text.primary)
                        Text("kg")
                            .font(.system(size: 12))
                            .foregroundColor(ColorsToken.Text.secondary)
                    }
                    .frame(width: 80)
                    .padding(.vertical, 4)
                    .background(
                        RoundedRectangle(cornerRadius: 8)
                            .fill(ColorsToken.Background.secondary.opacity(0.5))
                    )
                }
                .buttonStyle(PlainButtonStyle())
            }
            
            stepButton(systemName: "plus", disabled: false) {
                let newValue = (set.displayWeight ?? 0) + 2.5
                onValueChange("weight", newValue)
            }
        }
    }
    
    private var repsEditor: some View {
        HStack(spacing: Space.md) {
            stepButton(systemName: "minus", disabled: (set.displayReps ?? 1) <= 1) {
                let newValue = (set.displayReps ?? 10) - 1
                onValueChange("reps", max(1, newValue))
            }
            
            // Tappable value → TextField for direct keyboard input
            if isEditingText {
                VStack(spacing: 0) {
                    TextField("", text: $textInputValue)
                        .font(.system(size: 24, weight: .bold).monospacedDigit())
                        .keyboardType(.numberPad)
                        .multilineTextAlignment(.center)
                        .focused($textFieldFocused)
                        .frame(width: 70)
                        .onSubmit { commitTextInput() }
                        .onChange(of: textFieldFocused) { _, focused in
                            if !focused { commitTextInput() }
                        }
                    Text("reps")
                        .font(.system(size: 11))
                        .foregroundColor(ColorsToken.Text.secondary)
                }
                .frame(width: 80)
            } else {
                Button {
                    textInputValue = "\(set.displayReps ?? 10)"
                    isEditingText = true
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
                        textFieldFocused = true
                    }
                } label: {
                    VStack(spacing: 0) {
                        Text("\(set.displayReps ?? 10)")
                            .font(.system(size: 28, weight: .bold).monospacedDigit())
                            .foregroundColor(ColorsToken.Text.primary)
                        Text("reps")
                            .font(.system(size: 12))
                            .foregroundColor(ColorsToken.Text.secondary)
                    }
                    .frame(width: 70)
                    .padding(.vertical, 4)
                    .background(
                        RoundedRectangle(cornerRadius: 8)
                            .fill(ColorsToken.Background.secondary.opacity(0.5))
                    )
                }
                .buttonStyle(PlainButtonStyle())
            }
            
            stepButton(systemName: "plus", disabled: (set.displayReps ?? 0) >= 30) {
                let newValue = (set.displayReps ?? 10) + 1
                onValueChange("reps", min(30, newValue))
            }
        }
    }
    
    // MARK: - Text Input Commit
    
    private func commitTextInput() {
        isEditingText = false
        textFieldFocused = false
        
        let trimmed = textInputValue.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        
        switch selectedCell {
        case .weight:
            if let value = Double(trimmed.replacingOccurrences(of: ",", with: ".")) {
                let rounded = (value * 4).rounded() / 4  // Round to nearest 0.25kg
                onValueChange("weight", max(0, rounded))
            }
        case .reps:
            if let value = Int(trimmed) {
                onValueChange("reps", min(30, max(1, value)))
            }
        default:
            break
        }
        
        textInputValue = ""
    }
    
    private var rirEditor: some View {
        HStack(spacing: Space.sm) {
            ForEach(0...5, id: \.self) { rir in
                Button {
                    onValueChange("rir", rir)
                    UIImpactFeedbackGenerator(style: .light).impactOccurred()
                } label: {
                    Text("\(rir)")
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundColor(set.displayRir == rir ? .white : ColorsToken.Text.primary)
                        .frame(width: 42, height: 42)
                        .background(set.displayRir == rir ? rirColor(rir) : ColorsToken.Background.secondary)
                        .clipShape(Circle())
                }
                .buttonStyle(PlainButtonStyle())
            }
        }
    }
    
    // MARK: - Helpers
    
    private func stepButton(systemName: String, disabled: Bool, action: @escaping () -> Void) -> some View {
        Button {
            action()
            UIImpactFeedbackGenerator(style: .light).impactOccurred()
        } label: {
            Image(systemName: systemName)
                .font(.system(size: 20, weight: .semibold))
                .foregroundColor(disabled ? ColorsToken.Text.secondary.opacity(0.3) : ColorsToken.Brand.primary)
                .frame(width: 50, height: 50)
                .background(ColorsToken.Background.secondary)
                .clipShape(Circle())
        }
        .buttonStyle(PlainButtonStyle())
        .disabled(disabled)
    }
    
    private func formatWeight(_ weight: Double?) -> String {
        guard let w = weight else { return "—" }
        if w.truncatingRemainder(dividingBy: 1) == 0 {
            return "\(Int(w))"
        }
        return String(format: "%.1f", w)
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

struct FocusModeSetTypePickerSheet: View {
    let setId: String
    let exerciseId: String
    let currentType: FocusModeSetType
    let isFailure: Bool
    let onSelectType: (FocusModeSetType) -> Void
    let onToggleFailure: (Bool) -> Void
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
                    setTypeOption(type: .warmup, title: "Warm-up", icon: "flame", color: ColorsToken.Text.secondary)
                    Divider().padding(.leading, 56)
                    setTypeOption(type: .working, title: "Working Set", icon: "dumbbell", color: ColorsToken.Brand.primary)
                    Divider().padding(.leading, 56)
                    setTypeOption(type: .dropset, title: "Drop Set", icon: "arrow.down.circle", color: ColorsToken.State.warning)
                }
                .background(ColorsToken.Surface.card)
                
                // Failure toggle (separate from set type)
                Text("Modifiers")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(ColorsToken.Text.secondary)
                    .padding(.horizontal, Space.lg)
                    .padding(.top, Space.xl)
                    .padding(.bottom, Space.sm)
                
                VStack(spacing: 0) {
                    Button {
                        onToggleFailure(!isFailure)
                    } label: {
                        HStack(spacing: Space.md) {
                            Image(systemName: "flame.fill")
                                .font(.system(size: 18))
                                .foregroundColor(ColorsToken.State.error)
                                .frame(width: 32)
                            
                            VStack(alignment: .leading, spacing: 2) {
                                Text("Failure")
                                    .font(.system(size: 15, weight: .medium))
                                    .foregroundColor(ColorsToken.Text.primary)
                                Text("Mark this set as taken to failure")
                                    .font(.system(size: 12))
                                    .foregroundColor(ColorsToken.Text.secondary)
                            }
                            
                            Spacer()
                            
                            Image(systemName: isFailure ? "checkmark.circle.fill" : "circle")
                                .font(.system(size: 22))
                                .foregroundColor(isFailure ? ColorsToken.State.error : ColorsToken.Text.secondary.opacity(0.3))
                        }
                        .padding(.horizontal, Space.lg)
                        .padding(.vertical, 14)
                    }
                    .buttonStyle(PlainButtonStyle())
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
    
    private func setTypeOption(type: FocusModeSetType, title: String, icon: String, color: Color) -> some View {
        Button { onSelectType(type) } label: {
            HStack(spacing: Space.md) {
                Image(systemName: icon)
                    .font(.system(size: 18))
                    .foregroundColor(color)
                    .frame(width: 32)
                
                Text(title)
                    .font(.system(size: 15, weight: .medium))
                    .foregroundColor(ColorsToken.Text.primary)
                
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

// MARK: - Preview

#Preview {
    FocusModeSetGrid(
        exercise: FocusModeExercise(
            instanceId: "ex1",
            exerciseId: "bench-press",
            name: "Bench Press",
            position: 0,
            sets: [
                FocusModeSet(id: "s1", setType: .warmup, status: .done, targetWeight: 40, targetReps: 10, weight: 40, reps: 10),
                FocusModeSet(id: "s2", setType: .working, status: .done, targetWeight: 70, targetReps: 8, targetRir: 2, weight: 70, reps: 8, rir: 2),
                FocusModeSet(id: "s3", setType: .working, status: .planned, targetWeight: 70, targetReps: 8, targetRir: 2),
                FocusModeSet(id: "s4", setType: .working, status: .planned, targetWeight: 70, targetReps: 8, targetRir: 2)
            ]
        ),
        selectedCell: .constant(nil),
        onLogSet: { _, _, _, _, _ in },
        onPatchField: { _, _, _, _ in },
        onAddSet: { },
        onRemoveSet: { _ in }
    )
    .padding()
    .background(ColorsToken.Background.primary)
}
