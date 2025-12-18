import SwiftUI

public struct SessionPlanCard: View {
    private let model: CanvasCardModel
    @State private var editableExercises: [PlanExercise] = []
    @State private var expandedExerciseId: String? = nil
    @State private var showCardMenu: Bool = false
    @State private var exerciseMenuId: String? = nil
    @State private var exerciseForDetail: PlanExercise? = nil
    @Environment(\.cardActionHandler) private var handleAction
    
    public init(model: CanvasCardModel) {
        self.model = model
    }
    
    public var body: some View {
        CardContainer(status: model.status) {
            VStack(alignment: .leading, spacing: Space.sm) {
                // Header with menu
                cardHeader
                
                // Exercise list
                VStack(alignment: .leading, spacing: Space.xs) {
                    ForEach(editableExercises.indices, id: \.self) { index in
                        exerciseRow(exercise: editableExercises[index], index: index)
                    }
                }
                
                // Accept button
                if model.status == .proposed {
                    acceptButton
                }
            }
        }
        .onAppear {
            if case .sessionPlan(let exercises) = model.data {
                editableExercises = exercises
            }
        }
        .onChange(of: model.data) { newData in
            if case .sessionPlan(let exercises) = newData {
                editableExercises = exercises
            }
        }
        .sheet(item: $exerciseForDetail) { exercise in
            ExerciseDetailSheet(
                exerciseId: exercise.exerciseId,
                exerciseName: exercise.name,
                onDismiss: { exerciseForDetail = nil }
            )
        }
    }
    
    // MARK: - Card Header with Menu
    
    private var cardHeader: some View {
        HStack {
            CardHeader(
                title: model.title ?? "Session Plan",
                subtitle: model.subtitle,
                lane: model.lane,
                status: model.status,
                timestamp: model.publishedAt
            )
            Spacer()
            cardMenuTrigger
        }
    }
    
    private var cardMenuTrigger: some View {
        ZStack(alignment: .topTrailing) {
            Button(action: {
                withAnimation(.easeOut(duration: 0.15)) {
                    showCardMenu.toggle()
                    exerciseMenuId = nil
                }
            }) {
                Image(systemName: "ellipsis")
                    .font(.system(size: 16, weight: .medium))
                    .foregroundColor(ColorsToken.Text.secondary)
                    .frame(width: 32, height: 32)
                    .background(showCardMenu ? ColorsToken.Background.secondary : ColorsToken.Background.secondary.opacity(0.5))
                    .clipShape(Circle())
            }
            
            if showCardMenu {
                cardMenuDropdown
                    .offset(x: 0, y: 36)
            }
        }
    }
    
    private var cardMenuDropdown: some View {
        DropdownMenu(items: cardMenuItems) {
            withAnimation(.easeOut(duration: 0.15)) {
                showCardMenu = false
            }
        }
        .frame(minWidth: 180)
        .transition(.opacity.combined(with: .scale(scale: 0.95, anchor: .topTrailing)))
    }
    
    private var cardMenuItems: [DropdownMenuItem] {
        [
            DropdownMenuItem(title: "Accept Plan", icon: "checkmark.circle") {
                let action = CardAction(kind: "accept_plan", label: "Accept", style: .primary, payload: serializePlan())
                handleAction(action, model)
            },
            DropdownMenuItem(title: "Make Shorter", icon: "minus.circle") {
                fireAdjustment("Make this session shorter - reduce total sets or exercises")
            },
            DropdownMenuItem(title: "Make Harder", icon: "flame") {
                fireAdjustment("Make this session more challenging - increase intensity or volume")
            },
            DropdownMenuItem(title: "Regenerate", icon: "arrow.triangle.2.circlepath") {
                fireAdjustment("Regenerate this workout plan with different exercises")
            },
            DropdownMenuItem(title: "Dismiss", icon: "xmark.circle", isDestructive: true) {
                let action = CardAction(kind: "dismiss", label: "Dismiss", style: .destructive)
                handleAction(action, model)
            }
        ]
    }
    
    // MARK: - Exercise Row
    
    private func exerciseRow(exercise: PlanExercise, index: Int) -> some View {
        let isExpanded = expandedExerciseId == exercise.id
        let showMenu = exerciseMenuId == exercise.id
        
        return VStack(alignment: .leading, spacing: 0) {
            // Collapsed row
            HStack {
                Button(action: {
                    withAnimation(.easeInOut(duration: 0.2)) {
                        expandedExerciseId = isExpanded ? nil : exercise.id
                    }
                }) {
                    HStack {
                        Image(systemName: isExpanded ? "chevron.down" : "chevron.right")
                            .font(.system(size: 12, weight: .medium))
                            .foregroundColor(ColorsToken.Text.secondary)
                            .frame(width: 16)
                        
                        StatusTag("x\(exercise.sets)", kind: .info)
                        
                        MyonText(exercise.name, style: .body)
                            .foregroundColor(ColorsToken.Text.primary)
                        
                        Spacer()
                    }
                }
                .buttonStyle(PlainButtonStyle())
                
                // Exercise menu trigger
                ZStack(alignment: .topTrailing) {
                    Button(action: {
                        withAnimation(.easeOut(duration: 0.15)) {
                            exerciseMenuId = showMenu ? nil : exercise.id
                            showCardMenu = false
                        }
                    }) {
                        Image(systemName: "ellipsis")
                            .font(.system(size: 14))
                            .foregroundColor(ColorsToken.Text.secondary)
                            .frame(width: 28, height: 28)
                            .background(showMenu ? ColorsToken.Background.secondary : Color.clear)
                            .clipShape(Circle())
                    }
                    .buttonStyle(PlainButtonStyle())
                    
                    if showMenu {
                        exerciseMenuDropdown(exercise: exercise)
                            .offset(x: 0, y: 32)
                    }
                }
            }
            .padding(.vertical, Space.xs)
            
            // Expanded details
            if isExpanded {
                expandedContent(index: index)
                    .transition(.opacity.combined(with: .move(edge: .top)))
            }
        }
        .background(ColorsToken.Background.primary)
    }
    
    private func exerciseMenuDropdown(exercise: PlanExercise) -> some View {
        DropdownMenu(items: exerciseMenuItems(for: exercise)) {
            withAnimation(.easeOut(duration: 0.15)) {
                exerciseMenuId = nil
            }
        }
        .frame(minWidth: 200)
        .transition(.opacity.combined(with: .scale(scale: 0.95, anchor: .topTrailing)))
    }
    
    private func exerciseMenuItems(for exercise: PlanExercise) -> [DropdownMenuItem] {
        let muscles = exercise.primaryMuscles?.joined(separator: ", ") ?? "similar muscles"
        let equipment = exercise.equipment ?? "same equipment"
        
        return [
            DropdownMenuItem(title: "Learn About Exercise", icon: "book") {
                exerciseForDetail = exercise
            },
            DropdownMenuItem(title: "Swap (Same Muscles)", icon: "arrow.left.arrow.right") {
                fireSwap(exercise: exercise, reason: "same_muscles")
            },
            DropdownMenuItem(title: "Swap (Same Equipment)", icon: "dumbbell") {
                fireSwap(exercise: exercise, reason: "same_equipment")
            },
            DropdownMenuItem(title: "Swap (Ask AI)", icon: "sparkles") {
                fireSwap(exercise: exercise, reason: "ai_suggestion")
            },
            DropdownMenuItem(title: "Remove", icon: "trash", isDestructive: true) {
                withAnimation {
                    editableExercises.removeAll { $0.id == exercise.id }
                }
            }
        ]
    }
    
    // MARK: - Expanded Content
    
    @ViewBuilder
    private func expandedContent(index: Int) -> some View {
        VStack(alignment: .leading, spacing: Space.sm) {
            // Sets and Reps row
            HStack(spacing: Space.lg) {
                // Sets stepper
                VStack(alignment: .leading, spacing: 2) {
                    MyonText("Sets", style: .caption)
                        .foregroundColor(ColorsToken.Text.secondary)
                    stepper(
                        value: Binding(
                            get: { editableExercises[index].sets },
                            set: { editableExercises[index].sets = $0 }
                        ),
                        range: 1...10
                    )
                }
                
                // Reps stepper
                VStack(alignment: .leading, spacing: 2) {
                    MyonText("Reps", style: .caption)
                        .foregroundColor(ColorsToken.Text.secondary)
                    stepper(
                        value: Binding(
                            get: { editableExercises[index].reps },
                            set: { editableExercises[index].reps = $0 }
                        ),
                        range: 1...30
                    )
                }
                
                // RIR stepper
                VStack(alignment: .leading, spacing: 2) {
                    MyonText("RIR", style: .caption)
                        .foregroundColor(ColorsToken.Text.secondary)
                    stepper(
                        value: Binding(
                            get: { editableExercises[index].rir ?? 2 },
                            set: { editableExercises[index].rir = $0 }
                        ),
                        range: 0...5
                    )
                }
                
                Spacer()
            }
            
            // Weight input
            HStack(spacing: Space.sm) {
                MyonText("Weight", style: .caption)
                    .foregroundColor(ColorsToken.Text.secondary)
                
                TextField("--", value: Binding(
                    get: { editableExercises[index].weight },
                    set: { editableExercises[index].weight = $0 }
                ), format: .number)
                .keyboardType(.decimalPad)
                .textFieldStyle(.plain)
                .frame(width: 60)
                .padding(.horizontal, Space.sm)
                .padding(.vertical, 4)
                .background(ColorsToken.Background.secondary)
                .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.small))
                
                MyonText("kg", style: .caption)
                    .foregroundColor(ColorsToken.Text.secondary)
            }
            
            // Coach note if present
            if let note = editableExercises[index].coachNote, !note.isEmpty {
                HStack(spacing: Space.xs) {
                    Image(systemName: "text.bubble")
                        .font(.system(size: 12))
                        .foregroundColor(ColorsToken.Brand.primary)
                    MyonText(note, style: .caption)
                        .foregroundColor(ColorsToken.Text.secondary)
                }
            }
            
            // Primary muscles if present
            if let muscles = editableExercises[index].primaryMuscles, !muscles.isEmpty {
                HStack(spacing: Space.xs) {
                    Image(systemName: "figure.strengthtraining.traditional")
                        .font(.system(size: 12))
                        .foregroundColor(ColorsToken.Text.secondary)
                    MyonText(muscles.joined(separator: ", "), style: .caption)
                        .foregroundColor(ColorsToken.Text.secondary)
                }
            }
        }
        .padding(.leading, 28)
        .padding(.bottom, Space.sm)
    }
    
    // MARK: - Stepper Component
    
    private func stepper(value: Binding<Int>, range: ClosedRange<Int>) -> some View {
        HStack(spacing: 0) {
            Button(action: {
                if value.wrappedValue > range.lowerBound {
                    value.wrappedValue -= 1
                }
            }) {
                Image(systemName: "minus")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(value.wrappedValue <= range.lowerBound ? ColorsToken.Text.secondary.opacity(0.3) : ColorsToken.Text.primary)
                    .frame(width: 28, height: 28)
            }
            .disabled(value.wrappedValue <= range.lowerBound)
            
            Text("\(value.wrappedValue)")
                .font(.system(size: 14, weight: .medium))
                .foregroundColor(ColorsToken.Text.primary)
                .frame(width: 32)
            
            Button(action: {
                if value.wrappedValue < range.upperBound {
                    value.wrappedValue += 1
                }
            }) {
                Image(systemName: "plus")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(value.wrappedValue >= range.upperBound ? ColorsToken.Text.secondary.opacity(0.3) : ColorsToken.Text.primary)
                    .frame(width: 28, height: 28)
            }
            .disabled(value.wrappedValue >= range.upperBound)
        }
        .background(ColorsToken.Background.secondary)
        .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.small))
    }
    
    // MARK: - Accept Button
    
    private var acceptButton: some View {
        Button(action: {
            let action = CardAction(kind: "accept_plan", label: "Accept", style: .primary, payload: serializePlan())
            handleAction(action, model)
        }) {
            HStack {
                Image(systemName: "checkmark")
                MyonText("Accept Plan", style: .body)
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, Space.sm)
            .background(ColorsToken.Brand.primary)
            .foregroundColor(.white)
            .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.medium))
        }
        .buttonStyle(PlainButtonStyle())
        .padding(.top, Space.sm)
    }
    
    // MARK: - Actions
    
    private func fireAdjustment(_ instruction: String) {
        let planContext = serializePlanForAgent()
        let action = CardAction(
            kind: "adjust_plan",
            label: instruction,
            payload: ["instruction": instruction, "current_plan": planContext]
        )
        handleAction(action, model)
    }
    
    private func fireSwap(exercise: PlanExercise, reason: String) {
        let planContext = serializePlanForAgent()
        let muscles = exercise.primaryMuscles?.joined(separator: ", ") ?? "unknown"
        let equipment = exercise.equipment ?? "unknown"
        
        let instruction: String
        switch reason {
        case "same_muscles":
            instruction = "Swap \(exercise.name) for another exercise targeting \(muscles)"
        case "same_equipment":
            instruction = "Swap \(exercise.name) for another \(equipment) exercise"
        case "ai_suggestion":
            instruction = "Suggest a replacement for \(exercise.name) that fits this workout"
        default:
            instruction = "Swap \(exercise.name)"
        }
        
        let action = CardAction(
            kind: "swap_exercise",
            label: "Swap",
            payload: [
                "instruction": instruction,
                "exercise_id": exercise.exerciseId ?? "",
                "exercise_name": exercise.name,
                "swap_reason": reason,
                "current_plan": planContext
            ]
        )
        handleAction(action, model)
    }
    
    private func serializePlan() -> [String: String] {
        guard let data = try? JSONEncoder().encode(editableExercises),
              let json = String(data: data, encoding: .utf8) else {
            return [:]
        }
        return ["exercises_json": json]
    }
    
    private func serializePlanForAgent() -> String {
        editableExercises.enumerated().map { index, ex in
            var line = "\(index + 1). \(ex.name) - \(ex.sets) sets × \(ex.reps) reps"
            if let rir = ex.rir { line += " @ RIR \(rir)" }
            if let weight = ex.weight { line += ", \(Int(weight))kg" }
            return line
        }.joined(separator: "\n")
    }
}
