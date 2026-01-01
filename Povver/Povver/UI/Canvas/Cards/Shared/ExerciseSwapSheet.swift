import SwiftUI

/// Sheet for swapping an exercise - supports both AI suggestions and manual search
public struct ExerciseSwapSheet: View {
    let currentExercise: PlanExercise
    let onSwapWithAI: (ExerciseActionsRow.SwapReason, String) -> Void  // Reason + instruction
    let onSwapManual: (Exercise) -> Void  // Selected replacement exercise
    let onDismiss: () -> Void
    
    @State private var selectedTab: SwapTab = .aiSuggestions
    @State private var searchQuery: String = ""
    @State private var searchResults: [Exercise] = []
    @State private var isSearching: Bool = false
    @State private var errorMessage: String? = nil
    
    private let exerciseRepo = ExerciseRepository()
    
    enum SwapTab {
        case aiSuggestions
        case manualSearch
    }
    
    public var body: some View {
        NavigationView {
            VStack(spacing: 0) {
                // Current exercise info
                currentExerciseHeader
                
                // Tab picker
                Picker("", selection: $selectedTab) {
                    Text("AI Suggestions").tag(SwapTab.aiSuggestions)
                    Text("Search").tag(SwapTab.manualSearch)
                }
                .pickerStyle(.segmented)
                .padding(.horizontal, Space.lg)
                .padding(.bottom, Space.md)
                
                // Content
                switch selectedTab {
                case .aiSuggestions:
                    aiSuggestionsView
                case .manualSearch:
                    manualSearchView
                }
            }
            .background(ColorsToken.Background.primary)
            .navigationTitle("Swap Exercise")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Cancel") { onDismiss() }
                        .foregroundColor(ColorsToken.Text.secondary)
                }
            }
        }
        .presentationDetents([.large])
        .presentationDragIndicator(.visible)
    }
    
    // MARK: - Current Exercise Header
    
    private var currentExerciseHeader: some View {
        VStack(alignment: .leading, spacing: Space.xs) {
            Text("Currently:")
                .font(.system(size: 12, weight: .medium))
                .foregroundColor(ColorsToken.Text.secondary)
            
            HStack(spacing: Space.sm) {
                Image(systemName: "dumbbell")
                    .font(.system(size: 16))
                    .foregroundColor(ColorsToken.Brand.primary)
                
                VStack(alignment: .leading, spacing: 2) {
                    Text(currentExercise.name)
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundColor(ColorsToken.Text.primary)
                    
                    Text(currentExercise.summaryLine)
                        .font(.system(size: 13))
                        .foregroundColor(ColorsToken.Text.secondary)
                }
                
                Spacer()
            }
            .padding(Space.md)
            .background(ColorsToken.Surface.card)
            .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.medium))
        }
        .padding(.horizontal, Space.lg)
        .padding(.vertical, Space.md)
    }
    
    // MARK: - AI Suggestions View
    
    private var aiSuggestionsView: some View {
        ScrollView {
            VStack(spacing: Space.sm) {
                ForEach([
                    ExerciseActionsRow.SwapReason.sameMuscles,
                    .sameEquipment,
                    .differentAngle,
                    .aiSuggestion
                ], id: \.self) { reason in
                    aiOptionButton(reason: reason)
                }
            }
            .padding(.horizontal, Space.lg)
            .padding(.bottom, Space.lg)
        }
    }
    
    private func aiOptionButton(reason: ExerciseActionsRow.SwapReason) -> some View {
        let (instruction, _) = ExerciseActionsRow.buildSwapInstruction(
            exercise: currentExercise,
            reason: reason
        )
        
        return Button {
            onSwapWithAI(reason, instruction)
            onDismiss()
        } label: {
            HStack(spacing: Space.md) {
                Image(systemName: reason.icon)
                    .font(.system(size: 18))
                    .foregroundColor(ColorsToken.Brand.primary)
                    .frame(width: 32)
                
                VStack(alignment: .leading, spacing: 2) {
                    Text(reason.label)
                        .font(.system(size: 15, weight: .medium))
                        .foregroundColor(ColorsToken.Text.primary)
                    
                    Text(descriptionFor(reason))
                        .font(.system(size: 12))
                        .foregroundColor(ColorsToken.Text.secondary)
                        .lineLimit(2)
                }
                
                Spacer()
                
                Image(systemName: "chevron.right")
                    .font(.system(size: 12))
                    .foregroundColor(ColorsToken.Text.secondary.opacity(0.5))
            }
            .padding(Space.md)
            .background(ColorsToken.Surface.card)
            .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.medium))
        }
        .buttonStyle(PlainButtonStyle())
    }
    
    private func descriptionFor(_ reason: ExerciseActionsRow.SwapReason) -> String {
        let muscles = currentExercise.primaryMuscles?.first ?? "same muscles"
        let equipment = currentExercise.equipment ?? "similar equipment"
        
        switch reason {
        case .sameMuscles:
            return "Another \(muscles) exercise with different equipment"
        case .sameEquipment:
            return "Another \(equipment) exercise with a different angle"
        case .differentAngle:
            return "A different movement pattern targeting \(muscles)"
        case .aiSuggestion:
            return "Let the AI coach pick the best alternative based on your goals"
        case .manualSearch:
            return ""
        }
    }
    
    // MARK: - Manual Search View
    
    private var manualSearchView: some View {
        VStack(spacing: 0) {
            // Search bar
            HStack {
                Image(systemName: "magnifyingglass")
                    .foregroundColor(ColorsToken.Text.secondary)
                
                TextField("Search exercises...", text: $searchQuery)
                    .textFieldStyle(PlainTextFieldStyle())
                    .onSubmit { performSearch() }
                
                if !searchQuery.isEmpty {
                    Button { searchQuery = "" } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundColor(ColorsToken.Text.secondary)
                    }
                    .buttonStyle(PlainButtonStyle())
                }
            }
            .padding(Space.sm)
            .background(ColorsToken.Surface.card)
            .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.medium))
            .padding(.horizontal, Space.lg)
            .padding(.bottom, Space.md)
            
            // Results
            if isSearching {
                Spacer()
                ProgressView()
                    .progressViewStyle(.circular)
                Spacer()
            } else if let error = errorMessage {
                Spacer()
                Text(error)
                    .font(.system(size: 14))
                    .foregroundColor(ColorsToken.State.error)
                    .multilineTextAlignment(.center)
                    .padding()
                Spacer()
            } else if searchResults.isEmpty && !searchQuery.isEmpty {
                Spacer()
                VStack(spacing: Space.sm) {
                    Image(systemName: "magnifyingglass")
                        .font(.system(size: 40))
                        .foregroundColor(ColorsToken.Text.secondary.opacity(0.5))
                    Text("No exercises found")
                        .font(.system(size: 15))
                        .foregroundColor(ColorsToken.Text.secondary)
                }
                Spacer()
            } else if searchResults.isEmpty {
                Spacer()
                VStack(spacing: Space.sm) {
                    Image(systemName: "text.magnifyingglass")
                        .font(.system(size: 40))
                        .foregroundColor(ColorsToken.Text.secondary.opacity(0.5))
                    Text("Search for an exercise to swap")
                        .font(.system(size: 15))
                        .foregroundColor(ColorsToken.Text.secondary)
                }
                Spacer()
            } else {
                ScrollView {
                    LazyVStack(spacing: 0) {
                        ForEach(searchResults) { exercise in
                            exerciseResultRow(exercise)
                            Divider()
                        }
                    }
                }
            }
        }
    }
    
    private func exerciseResultRow(_ exercise: Exercise) -> some View {
        Button {
            onSwapManual(exercise)
            onDismiss()
        } label: {
            HStack(spacing: Space.md) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(exercise.name)
                        .font(.system(size: 15, weight: .medium))
                        .foregroundColor(ColorsToken.Text.primary)
                    
                    HStack(spacing: Space.sm) {
                        if !exercise.primaryMuscles.isEmpty {
                            Text(exercise.primaryMuscles.joined(separator: ", "))
                                .font(.system(size: 12))
                                .foregroundColor(ColorsToken.Text.secondary)
                        }
                        
                        if !exercise.equipment.isEmpty {
                            Text("• \(exercise.equipment.joined(separator: ", "))")
                                .font(.system(size: 12))
                                .foregroundColor(ColorsToken.Text.secondary)
                        }
                    }
                }
                
                Spacer()
                
                Image(systemName: "arrow.right.circle")
                    .font(.system(size: 18))
                    .foregroundColor(ColorsToken.Brand.primary)
            }
            .padding(.horizontal, Space.lg)
            .padding(.vertical, 12)
            .background(ColorsToken.Surface.card)
        }
        .buttonStyle(PlainButtonStyle())
    }
    
    // MARK: - Search
    
    private func performSearch() {
        guard !searchQuery.trimmingCharacters(in: .whitespaces).isEmpty else { return }
        
        isSearching = true
        errorMessage = nil
        
        Task {
            do {
                let allResults = try await exerciseRepo.searchExercises(query: searchQuery)
                // Limit to first 30 results
                let results = Array(allResults.prefix(30))
                await MainActor.run {
                    searchResults = results
                    isSearching = false
                }
            } catch {
                await MainActor.run {
                    errorMessage = "Search failed: \(error.localizedDescription)"
                    isSearching = false
                }
            }
        }
    }
}

// MARK: - Preview

#if DEBUG
struct ExerciseSwapSheet_Previews: PreviewProvider {
    static var previews: some View {
        ExerciseSwapSheet(
            currentExercise: PlanExercise(name: "Bench Press", sets: [
                PlanSet(type: .working, reps: 8, weight: 80, rir: 2)
            ]),
            onSwapWithAI: { reason, instruction in print("AI swap: \(reason) - \(instruction)") },
            onSwapManual: { exercise in print("Manual swap to: \(exercise.name)") },
            onDismiss: { print("Dismissed") }
        )
    }
}
#endif
