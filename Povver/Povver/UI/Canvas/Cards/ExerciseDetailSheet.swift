import SwiftUI

/// Exercise detail sheet - uses SheetScaffold for v1.1 consistency
public struct ExerciseDetailSheet: View {
    let exerciseId: String?
    let exerciseName: String
    let onDismiss: () -> Void
    
    @State private var exercise: Exercise? = nil
    @State private var isLoading: Bool = true
    @State private var error: String? = nil
    
    private let repository = ExerciseRepository()
    
    public init(exerciseId: String?, exerciseName: String, onDismiss: @escaping () -> Void) {
        self.exerciseId = exerciseId
        self.exerciseName = exerciseName
        self.onDismiss = onDismiss
    }
    
    public var body: some View {
        SheetScaffold(
            title: exerciseName,
            cancelTitle: "Done",  // Use "Done" as the cancel button text
            doneTitle: nil,  // Hide the done button (single button pattern)
            onCancel: { onDismiss() }
        ) {
            if isLoading {
                loadingView
            } else if let error = error {
                errorView(error)
            } else if let exercise = exercise {
                exerciseContent(exercise)
            } else {
                notFoundView
            }
        }
        .task {
            await loadExercise()
        }
    }
    
    // MARK: - Loading
    
    private var loadingView: some View {
        VStack(spacing: Space.md) {
            ProgressView()
                .progressViewStyle(.circular)
            PovverText("Loading exercise details…", style: .body)
                .foregroundColor(Color.textSecondary)
        }
        .frame(maxWidth: .infinity, minHeight: 300)
    }
    
    private func errorView(_ message: String) -> some View {
        VStack(spacing: Space.md) {
            Image(systemName: "exclamationmark.triangle")
                .font(.system(size: 40))
                .foregroundColor(Color.destructive)
            PovverText("Failed to load exercise", style: .headline)
            PovverText(message, style: .caption)
                .foregroundColor(Color.textSecondary)
            Button("Retry") {
                Task { await loadExercise() }
            }
            .buttonStyle(.borderedProminent)
        }
        .frame(maxWidth: .infinity, minHeight: 300)
    }
    
    private var notFoundView: some View {
        VStack(spacing: Space.md) {
            Image(systemName: "questionmark.circle")
                .font(.system(size: 40))
                .foregroundColor(Color.textSecondary)
            PovverText("Exercise not found", style: .headline)
            PovverText("This exercise may not be in the catalog yet.", style: .body)
                .foregroundColor(Color.textSecondary)
        }
        .frame(maxWidth: .infinity, minHeight: 300)
    }
    
    // MARK: - Content
    
    private func exerciseContent(_ ex: Exercise) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Space.lg) {
                // Header info
                headerSection(ex)
                
                // Muscles
                musclesSection(ex)
                
                // Execution notes
                if !ex.executionNotes.isEmpty {
                    section(title: "How to Perform", icon: "list.number") {
                        VStack(alignment: .leading, spacing: Space.sm) {
                            ForEach(ex.executionNotes.indices, id: \.self) { index in
                                HStack(alignment: .top, spacing: Space.sm) {
                                    Text("\(index + 1).")
                                        .font(.system(size: 14, weight: .medium))
                                        .foregroundColor(Color.accent)
                                        .frame(width: 20, alignment: .leading)
                                    PovverText(ex.executionNotes[index], style: .body)
                                        .foregroundColor(Color.textPrimary)
                                }
                            }
                        }
                    }
                }
                
                // Common mistakes
                if !ex.commonMistakes.isEmpty {
                    section(title: "Common Mistakes", icon: "exclamationmark.triangle") {
                        VStack(alignment: .leading, spacing: Space.sm) {
                            ForEach(ex.commonMistakes, id: \.self) { mistake in
                                HStack(alignment: .top, spacing: Space.sm) {
                                    Image(systemName: "xmark.circle.fill")
                                        .font(.system(size: 14))
                                        .foregroundColor(Color.destructive)
                                    PovverText(mistake, style: .body)
                                        .foregroundColor(Color.textPrimary)
                                }
                            }
                        }
                    }
                }
                
                // Programming notes
                if !ex.programmingNotes.isEmpty {
                    section(title: "Programming Tips", icon: "lightbulb") {
                        VStack(alignment: .leading, spacing: Space.sm) {
                            ForEach(ex.programmingNotes, id: \.self) { note in
                                HStack(alignment: .top, spacing: Space.sm) {
                                    Image(systemName: "arrow.right.circle.fill")
                                        .font(.system(size: 14))
                                        .foregroundColor(Color.accent)
                                    PovverText(note, style: .body)
                                        .foregroundColor(Color.textPrimary)
                                }
                            }
                        }
                    }
                }
                
                // Suitability notes
                if !ex.suitabilityNotes.isEmpty {
                    section(title: "Best Suited For", icon: "person.fill.checkmark") {
                        VStack(alignment: .leading, spacing: Space.sm) {
                            ForEach(ex.suitabilityNotes, id: \.self) { note in
                                HStack(alignment: .top, spacing: Space.sm) {
                                    Image(systemName: "checkmark.circle.fill")
                                        .font(.system(size: 14))
                                        .foregroundColor(Color.success)
                                    PovverText(note, style: .body)
                                        .foregroundColor(Color.textPrimary)
                                }
                            }
                        }
                    }
                }
                
                Spacer(minLength: Space.xl)
            }
            .padding(Space.lg)
        }
    }
    
    private func headerSection(_ ex: Exercise) -> some View {
        VStack(alignment: .leading, spacing: Space.md) {
            // Category & Level badges
            HStack(spacing: Space.sm) {
                StatusTag(ex.capitalizedCategory, kind: .info)
                StatusTag(ex.capitalizedLevel, kind: .info)
                if let unilateral = ex.metadata.unilateral, unilateral {
                    StatusTag("Unilateral", kind: .info)
                }
            }
            
            // Equipment
            if !ex.equipment.isEmpty {
                HStack(spacing: Space.xs) {
                    Image(systemName: "dumbbell")
                        .font(.system(size: 14))
                        .foregroundColor(Color.textSecondary)
                    PovverText(ex.capitalizedEquipment, style: .body)
                        .foregroundColor(Color.textSecondary)
                }
            }
            
            // Movement type
            HStack(spacing: Space.xs) {
                Image(systemName: "arrow.left.and.right")
                    .font(.system(size: 14))
                    .foregroundColor(Color.textSecondary)
                PovverText(ex.capitalizedMovementType, style: .body)
                    .foregroundColor(Color.textSecondary)
                if let plane = ex.metadata.planeOfMotion {
                    PovverText("• \(plane.capitalized)", style: .body)
                        .foregroundColor(Color.textSecondary)
                }
            }
            
            // Stimulus tags
            if !ex.stimulusTags.isEmpty {
                HStack(spacing: Space.xs) {
                    Image(systemName: "bolt.fill")
                        .font(.system(size: 14))
                        .foregroundColor(Color.accent)
                    PovverText(ex.stimulusTags.map { $0.capitalized }.joined(separator: ", "), style: .caption)
                        .foregroundColor(Color.textSecondary)
                }
            }
        }
        .padding(Space.md)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.surface)
        .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.medium))
    }
    
    private func musclesSection(_ ex: Exercise) -> some View {
        section(title: "Target Muscles", icon: "figure.strengthtraining.traditional") {
            VStack(alignment: .leading, spacing: Space.md) {
                // Primary muscles
                VStack(alignment: .leading, spacing: Space.xs) {
                    PovverText("Primary", style: .caption)
                        .foregroundColor(Color.textSecondary)
                    FlowLayout(spacing: Space.xs) {
                        ForEach(ex.primaryMuscles, id: \.self) { muscle in
                            muscleBadge(muscle, isPrimary: true, contribution: ex.getContribution(for: muscle))
                        }
                    }
                }
                
                // Secondary muscles
                if !ex.secondaryMuscles.isEmpty {
                    VStack(alignment: .leading, spacing: Space.xs) {
                        PovverText("Secondary", style: .caption)
                            .foregroundColor(Color.textSecondary)
                        FlowLayout(spacing: Space.xs) {
                            ForEach(ex.secondaryMuscles, id: \.self) { muscle in
                                muscleBadge(muscle, isPrimary: false, contribution: ex.getContribution(for: muscle))
                            }
                        }
                    }
                }
            }
        }
    }
    
    private func muscleBadge(_ muscle: String, isPrimary: Bool, contribution: Double?) -> some View {
        HStack(spacing: 4) {
            Text(muscle.capitalized)
                .font(.system(size: 13, weight: isPrimary ? .medium : .regular))
            if let contrib = contribution {
                Text(String(format: "%.0f%%", contrib * 100))
                    .font(.system(size: 11))
                    .foregroundColor(Color.textSecondary)
            }
        }
        .padding(.horizontal, Space.sm)
        .padding(.vertical, 4)
        .background(isPrimary ? Color.accent.opacity(0.15) : Color.surfaceElevated)
        .foregroundColor(isPrimary ? Color.accent : Color.textPrimary)
        .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.small))
    }
    
    private func section<Content: View>(title: String, icon: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: Space.sm) {
            HStack(spacing: Space.xs) {
                Image(systemName: icon)
                    .font(.system(size: 16, weight: .medium))
                    .foregroundColor(Color.accent)
                PovverText(title, style: .headline)
            }
            content()
        }
    }
    
    // MARK: - Data Loading
    
    private func loadExercise() async {
        isLoading = true
        error = nil
        
        print("[ExerciseDetailSheet] Loading exercise: id=\(exerciseId ?? "nil") name=\(exerciseName)")
        
        do {
            // Try by ID first
            if let id = exerciseId, !id.isEmpty {
                print("[ExerciseDetailSheet] Trying to read by ID: \(id)")
                exercise = try await repository.read(id: id)
                if exercise != nil {
                    print("[ExerciseDetailSheet] Found by ID: \(exercise!.name)")
                } else {
                    print("[ExerciseDetailSheet] Not found by ID, will try name search")
                }
            }
            
            // If not found by ID, search by name (case-insensitive)
            if exercise == nil {
                print("[ExerciseDetailSheet] Searching all exercises...")
                let allExercises = try await repository.list()
                print("[ExerciseDetailSheet] Got \(allExercises.count) exercises from list()")
                
                let searchName = exerciseName.lowercased()
                    .trimmingCharacters(in: .whitespacesAndNewlines)
                
                // Exact match first
                exercise = allExercises.first { $0.name.lowercased() == searchName }
                if exercise != nil {
                    print("[ExerciseDetailSheet] Found by exact name match: \(exercise!.name)")
                }
                
                // Contains match fallback
                if exercise == nil {
                    exercise = allExercises.first { $0.name.lowercased().contains(searchName) || searchName.contains($0.name.lowercased()) }
                    if exercise != nil {
                        print("[ExerciseDetailSheet] Found by contains match: \(exercise!.name)")
                    }
                }
                
                if exercise == nil {
                    print("[ExerciseDetailSheet] Exercise not found. Sample names: \(allExercises.prefix(5).map { $0.name })")
                }
            }
        } catch {
            print("[ExerciseDetailSheet] Error: \(error)")
            self.error = error.localizedDescription
        }
        
        isLoading = false
    }
}

// MARK: - Flow Layout for Tags

struct FlowLayout: Layout {
    var spacing: CGFloat = 8
    
    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let result = arrangeSubviews(proposal: proposal, subviews: subviews)
        return result.size
    }
    
    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let result = arrangeSubviews(proposal: proposal, subviews: subviews)
        for (index, frame) in result.frames.enumerated() {
            subviews[index].place(at: CGPoint(x: bounds.minX + frame.minX, y: bounds.minY + frame.minY), proposal: .init(frame.size))
        }
    }
    
    private func arrangeSubviews(proposal: ProposedViewSize, subviews: Subviews) -> (size: CGSize, frames: [CGRect]) {
        let maxWidth = proposal.width ?? .infinity
        var frames: [CGRect] = []
        var x: CGFloat = 0
        var y: CGFloat = 0
        var rowHeight: CGFloat = 0
        
        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if x + size.width > maxWidth, x > 0 {
                x = 0
                y += rowHeight + spacing
                rowHeight = 0
            }
            frames.append(CGRect(origin: CGPoint(x: x, y: y), size: size))
            x += size.width + spacing
            rowHeight = max(rowHeight, size.height)
        }
        
        let height = y + rowHeight
        return (CGSize(width: maxWidth, height: height), frames)
    }
}
