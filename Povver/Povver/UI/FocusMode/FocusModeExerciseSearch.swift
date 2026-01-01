/**
 * FocusModeExerciseSearch.swift
 * 
 * Exercise search sheet for Focus Mode workout.
 * Uses existing ExercisesViewModel for data fetching.
 * Optimized for quick gym use - large tap targets, fast filtering.
 */

import SwiftUI

struct FocusModeExerciseSearch: View {
    @Environment(\.dismiss) private var dismiss
    @StateObject private var viewModel = ExercisesViewModel()
    
    let onSelect: (Exercise) -> Void
    
    @State private var searchText = ""
    @State private var selectedMuscleGroup: String?
    @State private var showingExerciseDetail: Exercise?
    
    // Actual primary muscles from the data (populated from viewModel)
    private var availableMuscles: [String] {
        viewModel.primaryMuscles.sorted()
    }
    
    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                // Search bar
                searchBar
                
                // Quick muscle filter chips - use actual muscles from data
                if !availableMuscles.isEmpty {
                    muscleFilterChips
                }
                
                // Exercise list
                if viewModel.isLoading {
                    loadingView
                } else if viewModel.exercises.isEmpty {
                    emptyView
                } else {
                    exerciseList
                }
            }
            .background(ColorsToken.Background.primary)
            .navigationTitle("Add Exercise")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Cancel") { dismiss() }
                        .foregroundColor(ColorsToken.Text.secondary)
                }
            }
        }
        .task {
            await viewModel.loadExercises()
        }
        .onChange(of: searchText) { _, newValue in
            Task {
                await viewModel.searchExercises(query: newValue)
            }
        }
        .sheet(item: $showingExerciseDetail) { exercise in
            FocusModeExerciseDetailSheet(exercise: exercise)
        }
    }
    
    // MARK: - Search Bar
    
    private var searchBar: some View {
        HStack(spacing: Space.sm) {
            Image(systemName: "magnifyingglass")
                .foregroundColor(ColorsToken.Text.secondary)
            
            TextField("Search exercises...", text: $searchText)
                .textFieldStyle(PlainTextFieldStyle())
                .font(.system(size: 16))
                .autocorrectionDisabled()
                .textInputAutocapitalization(.never)
            
            if !searchText.isEmpty {
                Button {
                    searchText = ""
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .foregroundColor(ColorsToken.Text.secondary)
                }
            }
        }
        .padding(.horizontal, Space.md)
        .padding(.vertical, 12)
        .background(ColorsToken.Surface.card)
        .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.medium))
        .padding(.horizontal, Space.md)
        .padding(.vertical, Space.sm)
    }
    
    // MARK: - Muscle Filter Chips
    
    private var muscleFilterChips: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: Space.sm) {
                // All chip
                FilterChip(
                    label: "All",
                    isSelected: selectedMuscleGroup == nil,
                    onTap: {
                        selectedMuscleGroup = nil
                        Task {
                            await viewModel.filterByPrimaryMuscle(nil)
                        }
                    }
                )
                
                ForEach(availableMuscles.prefix(8), id: \.self) { muscle in
                    FilterChip(
                        label: muscle.capitalized.replacingOccurrences(of: "_", with: " "),
                        isSelected: selectedMuscleGroup == muscle,
                        onTap: {
                            if selectedMuscleGroup == muscle {
                                selectedMuscleGroup = nil
                                Task { await viewModel.filterByPrimaryMuscle(nil) }
                            } else {
                                selectedMuscleGroup = muscle
                                Task { await viewModel.filterByPrimaryMuscle(muscle) }
                            }
                        }
                    )
                }
            }
            .padding(.horizontal, Space.md)
        }
        .padding(.bottom, Space.sm)
    }
    
    // MARK: - Exercise List
    
    private var exerciseList: some View {
        ScrollView {
            LazyVStack(spacing: 0) {
                ForEach(viewModel.exercises) { exercise in
                    ExerciseRow(
                        exercise: exercise,
                        onTap: {
                            onSelect(exercise)
                            dismiss()
                        },
                        onInfo: {
                            showingExerciseDetail = exercise
                        }
                    )
                    
                    Divider()
                        .padding(.leading, Space.md)
                }
            }
            .padding(.bottom, Space.xl)
        }
    }
    
    // MARK: - Loading View
    
    private var loadingView: some View {
        VStack {
            Spacer()
            ProgressView()
                .scaleEffect(1.2)
            Text("Loading exercises...")
                .font(.system(size: 14))
                .foregroundColor(ColorsToken.Text.secondary)
                .padding(.top, Space.md)
            Spacer()
        }
    }
    
    // MARK: - Empty View
    
    private var emptyView: some View {
        VStack(spacing: Space.md) {
            Spacer()
            Text("No exercises found")
                .font(.system(size: 16, weight: .medium))
                .foregroundColor(ColorsToken.Text.secondary)
            if !searchText.isEmpty {
                Text("Try a different search term")
                    .font(.system(size: 14))
                    .foregroundColor(ColorsToken.Text.muted)
            }
            if selectedMuscleGroup != nil {
                Button("Clear filter") {
                    selectedMuscleGroup = nil
                    Task { await viewModel.filterByPrimaryMuscle(nil) }
                }
                .font(.system(size: 14, weight: .medium))
                .foregroundColor(ColorsToken.Brand.primary)
            }
            Spacer()
        }
    }
}

// MARK: - Filter Chip

private struct FilterChip: View {
    let label: String
    let isSelected: Bool
    let onTap: () -> Void
    
    var body: some View {
        Button(action: onTap) {
            Text(label)
                .font(.system(size: 13, weight: isSelected ? .semibold : .medium))
                .foregroundColor(isSelected ? .white : ColorsToken.Text.primary)
                .padding(.horizontal, 14)
                .padding(.vertical, 8)
                .background(isSelected ? ColorsToken.Brand.primary : ColorsToken.Surface.card)
                .clipShape(Capsule())
        }
        .buttonStyle(PlainButtonStyle())
    }
}

// MARK: - Exercise Row (Simplified - no icons)

private struct ExerciseRow: View {
    let exercise: Exercise
    let onTap: () -> Void
    let onInfo: () -> Void
    
    var body: some View {
        HStack(spacing: Space.md) {
            // Exercise info - tap to add
            Button(action: onTap) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(exercise.capitalizedName)
                        .font(.system(size: 15, weight: .medium))
                        .foregroundColor(ColorsToken.Text.primary)
                        .lineLimit(1)
                    
                    Text(exerciseSubtitle)
                        .font(.system(size: 13))
                        .foregroundColor(ColorsToken.Text.secondary)
                        .lineLimit(1)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .buttonStyle(PlainButtonStyle())
            
            // Info button
            Button(action: onInfo) {
                Image(systemName: "info.circle")
                    .font(.system(size: 18))
                    .foregroundColor(ColorsToken.Text.secondary)
                    .frame(width: 32, height: 32)
            }
            .buttonStyle(PlainButtonStyle())
            
            // Add button
            Button(action: onTap) {
                Image(systemName: "plus.circle.fill")
                    .font(.system(size: 22))
                    .foregroundColor(ColorsToken.Brand.primary)
            }
            .buttonStyle(PlainButtonStyle())
        }
        .padding(.horizontal, Space.md)
        .padding(.vertical, 12)
        .contentShape(Rectangle())
    }
    
    private var exerciseSubtitle: String {
        let muscles = exercise.capitalizedPrimaryMuscles.joined(separator: ", ")
        let equipment = exercise.capitalizedEquipment
        
        if !muscles.isEmpty && !equipment.isEmpty {
            return "\(muscles) • \(equipment)"
        } else if !muscles.isEmpty {
            return muscles
        } else if !equipment.isEmpty {
            return equipment
        }
        return ""
    }
}

// MARK: - Exercise Detail Sheet (Focus Mode variant)

struct FocusModeExerciseDetailSheet: View {
    let exercise: Exercise
    @Environment(\.dismiss) private var dismiss
    
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: Space.lg) {
                    // Header
                    VStack(alignment: .leading, spacing: Space.sm) {
                        Text(exercise.capitalizedName)
                            .font(.system(size: 24, weight: .bold))
                            .foregroundColor(ColorsToken.Text.primary)
                        
                        if !exercise.capitalizedEquipment.isEmpty {
                            Label(exercise.capitalizedEquipment, systemImage: "dumbbell")
                                .font(.system(size: 14))
                                .foregroundColor(ColorsToken.Text.secondary)
                        }
                    }
                    
                    Divider()
                    
                    // Muscles
                    if !exercise.primaryMuscles.isEmpty {
                        infoSection(title: "Primary Muscles") {
                            Text(exercise.capitalizedPrimaryMuscles.joined(separator: ", "))
                                .font(.system(size: 15))
                                .foregroundColor(ColorsToken.Text.primary)
                        }
                    }
                    
                    if !exercise.secondaryMuscles.isEmpty {
                        infoSection(title: "Secondary Muscles") {
                            Text(exercise.capitalizedSecondaryMuscles.joined(separator: ", "))
                                .font(.system(size: 15))
                                .foregroundColor(ColorsToken.Text.primary)
                        }
                    }
                    
                    // Movement info
                    if !exercise.movementType.isEmpty {
                        infoSection(title: "Movement Type") {
                            Text(exercise.capitalizedMovementType)
                                .font(.system(size: 15))
                                .foregroundColor(ColorsToken.Text.primary)
                        }
                    }
                    
                    // Level
                    if !exercise.level.isEmpty {
                        infoSection(title: "Difficulty") {
                            Text(exercise.capitalizedLevel)
                                .font(.system(size: 15))
                                .foregroundColor(ColorsToken.Text.primary)
                        }
                    }
                    
                    // Execution notes
                    if !exercise.executionNotes.isEmpty {
                        infoSection(title: "Execution Notes") {
                            ForEach(exercise.executionNotes, id: \.self) { note in
                                HStack(alignment: .top, spacing: Space.sm) {
                                    Text("•")
                                    Text(note)
                                }
                                .font(.system(size: 14))
                                .foregroundColor(ColorsToken.Text.primary)
                            }
                        }
                    }
                    
                    // Common mistakes
                    if !exercise.commonMistakes.isEmpty {
                        infoSection(title: "Common Mistakes") {
                            ForEach(exercise.commonMistakes, id: \.self) { mistake in
                                HStack(alignment: .top, spacing: Space.sm) {
                                    Text("•")
                                    Text(mistake)
                                }
                                .font(.system(size: 14))
                                .foregroundColor(ColorsToken.Text.primary)
                            }
                        }
                    }
                }
                .padding(Space.lg)
            }
            .background(ColorsToken.Background.primary)
            .navigationTitle("Exercise Details")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }
    
    private func infoSection<Content: View>(title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: Space.sm) {
            Text(title)
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(ColorsToken.Text.secondary)
                .textCase(.uppercase)
            
            content()
        }
    }
}

// MARK: - Preview

#Preview {
    FocusModeExerciseSearch { exercise in
        print("Selected: \(exercise.name)")
    }
}
