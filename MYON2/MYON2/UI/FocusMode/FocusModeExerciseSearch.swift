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
    
    // Quick access muscle groups
    private let muscleGroups = ["Chest", "Back", "Shoulders", "Arms", "Legs", "Core"]
    
    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                // Search bar
                searchBar
                
                // Quick muscle filter chips
                muscleFilterChips
                
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
        .onChange(of: searchText) { newValue in
            Task {
                await viewModel.searchExercises(query: newValue)
            }
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
                
                ForEach(muscleGroups, id: \.self) { muscle in
                    FilterChip(
                        label: muscle,
                        isSelected: selectedMuscleGroup == muscle.lowercased(),
                        onTap: {
                            let muscleValue = muscle.lowercased()
                            if selectedMuscleGroup == muscleValue {
                                selectedMuscleGroup = nil
                                Task { await viewModel.filterByPrimaryMuscle(nil) }
                            } else {
                                selectedMuscleGroup = muscleValue
                                Task { await viewModel.filterByPrimaryMuscle(muscleValue) }
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
                    ExerciseRow(exercise: exercise) {
                        onSelect(exercise)
                        dismiss()
                    }
                    
                    Divider()
                        .padding(.leading, 60)
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
        VStack {
            Spacer()
            Image(systemName: "dumbbell")
                .font(.system(size: 40))
                .foregroundColor(ColorsToken.Text.secondary)
            Text("No exercises found")
                .font(.system(size: 16, weight: .medium))
                .foregroundColor(ColorsToken.Text.secondary)
                .padding(.top, Space.md)
            if !searchText.isEmpty {
                Text("Try a different search term")
                    .font(.system(size: 14))
                    .foregroundColor(ColorsToken.Text.tertiary)
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

// MARK: - Exercise Row

private struct ExerciseRow: View {
    let exercise: Exercise
    let onTap: () -> Void
    
    var body: some View {
        Button(action: onTap) {
            HStack(spacing: Space.md) {
                // Exercise icon/avatar
                exerciseIcon
                
                // Exercise info
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
                
                Spacer()
                
                // Add indicator
                Image(systemName: "plus.circle")
                    .font(.system(size: 20))
                    .foregroundColor(ColorsToken.Brand.primary)
            }
            .padding(.horizontal, Space.md)
            .padding(.vertical, 12)
            .contentShape(Rectangle())
        }
        .buttonStyle(PlainButtonStyle())
    }
    
    private var exerciseIcon: some View {
        ZStack {
            Circle()
                .fill(muscleGroupColor.opacity(0.15))
                .frame(width: 44, height: 44)
            
            Image(systemName: muscleGroupIcon)
                .font(.system(size: 18))
                .foregroundColor(muscleGroupColor)
        }
    }
    
    private var exerciseSubtitle: String {
        let parts = [
            exercise.capitalizedEquipment,
            exercise.capitalizedPrimaryMuscles.joined(separator: ", ")
        ].filter { !$0.isEmpty }
        return parts.joined(separator: " • ")
    }
    
    private var muscleGroupColor: Color {
        let primary = exercise.primaryMuscles.first?.lowercased() ?? ""
        switch primary {
        case _ where primary.contains("chest"): return ColorsToken.Brand.primary
        case _ where primary.contains("back"), _ where primary.contains("lat"): return .orange
        case _ where primary.contains("shoulder"), _ where primary.contains("delt"): return .purple
        case _ where primary.contains("bicep"), _ where primary.contains("tricep"), _ where primary.contains("arm"): return .green
        case _ where primary.contains("quad"), _ where primary.contains("hamstring"), _ where primary.contains("glute"), _ where primary.contains("leg"): return .red
        case _ where primary.contains("core"), _ where primary.contains("ab"): return .yellow
        default: return ColorsToken.Text.secondary
        }
    }
    
    private var muscleGroupIcon: String {
        let primary = exercise.primaryMuscles.first?.lowercased() ?? ""
        switch primary {
        case _ where primary.contains("chest"): return "figure.arms.open"
        case _ where primary.contains("back"), _ where primary.contains("lat"): return "figure.mixed.cardio"
        case _ where primary.contains("shoulder"), _ where primary.contains("delt"): return "figure.martial.arts"
        case _ where primary.contains("bicep"), _ where primary.contains("tricep"), _ where primary.contains("arm"): return "figure.strengthtraining.functional"
        case _ where primary.contains("quad"), _ where primary.contains("hamstring"), _ where primary.contains("glute"), _ where primary.contains("leg"): return "figure.walk"
        case _ where primary.contains("core"), _ where primary.contains("ab"): return "figure.core.training"
        default: return "dumbbell"
        }
    }
}

// MARK: - Preview

#Preview {
    FocusModeExerciseSearch { exercise in
        print("Selected: \(exercise.name)")
    }
}
