import SwiftUI

public struct SessionPlanCard: View {
    private let model: CanvasCardModel
    @State private var editableExercises: [PlanExercise] = []
    @State private var expandedExerciseId: String? = nil
    @State private var showCardMenu: Bool = false
    @State private var exerciseForAction: PlanExercise? = nil
    @Environment(\.cardActionHandler) private var handleAction
    
    public init(model: CanvasCardModel) {
        self.model = model
    }
    
    public var body: some View {
        CardContainer(status: model.status) {
            VStack(alignment: .leading, spacing: Space.sm) {
                // Header with menu
                HStack {
                    CardHeader(
                        title: model.title ?? "Session Plan",
                        subtitle: model.subtitle,
                        lane: model.lane,
                        status: model.status,
                        timestamp: model.publishedAt
                    )
                    Spacer()
                    cardMenuButton
                }
                
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
        .confirmationDialog("Plan Options", isPresented: $showCardMenu, titleVisibility: .visible) {
            cardMenuOptions
        }
        .confirmationDialog(
            exerciseForAction?.name ?? "Exercise",
            isPresented: Binding(
                get: { exerciseForAction != nil },
                set: { if !$0 { exerciseForAction = nil } }
            ),
            titleVisibility: .visible
        ) {
            exerciseMenuOptions
        }
    }
    
    // MARK: - Card Menu
    
    private var cardMenuButton: some View {
        Button(action: { showCardMenu = true }) {
            Image(systemName: "ellipsis")
                .font(.system(size: 16, weight: .medium))
                .foregroundColor(ColorsToken.Text.secondary)
                .frame(width: 32, height: 32)
                .background(ColorsToken.Background.secondary.opacity(0.5))
                .clipShape(Circle())
        }
    }
    
    @ViewBuilder
    private var cardMenuOptions: some View {
        Button("Accept Plan") {
            let action = CardAction(kind: "accept_plan", label: "Accept", style: .primary, payload: serializePlan())
            handleAction(action, model)
        }
        Button("Make it Shorter") {
            fireAdjustment("Make this session shorter - reduce total sets or exercises")
        }
        Button("Make it Harder") {
            fireAdjustment("Make this session more challenging - increase intensity or volume")
        }
        Button("Regenerate") {
            fireAdjustment("Regenerate this workout plan with different exercises")
        }
        Button("Dismiss", role: .destructive) {
            let action = CardAction(kind: "dismiss", label: "Dismiss", style: .destructive)
            handleAction(action, model)
        }
        Button("Cancel", role: .cancel) { }
    }
    
    // MARK: - Exercise Row
    
    private func exerciseRow(exercise: PlanExercise, index: Int) -> some View {
        let isExpanded = expandedExerciseId == exercise.id
        
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
                
                // Exercise menu button
                Button(action: { exerciseForAction = exercise }) {
                    Image(systemName: "ellipsis")
                        .font(.system(size: 14))
                        .foregroundColor(ColorsToken.Text.secondary)
                        .frame(width: 28, height: 28)
                }
                .buttonStyle(PlainButtonStyle())
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
    
    // MARK: - Exercise Menu
    
    @ViewBuilder
    private var exerciseMenuOptions: some View {
        Button("Learn About Exercise") {
            if let ex = exerciseForAction {
                let action = CardAction(kind: "learn_exercise", label: "Learn", payload: ["exercise_id": ex.exerciseId ?? "", "name": ex.name])
                handleAction(action, model)
            }
        }
        
        Button("Swap → Same Muscles") {
            if let ex = exerciseForAction {
                fireSwap(exercise: ex, reason: "same_muscles")
            }
        }
        
        Button("Swap → Same Equipment") {
            if let ex = exerciseForAction {
                fireSwap(exercise: ex, reason: "same_equipment")
            }
        }
        
        Button("Swap → Ask AI") {
            if let ex = exerciseForAction {
                fireSwap(exercise: ex, reason: "ai_suggestion")
            }
        }
        
        Button("Remove", role: .destructive) {
            if let ex = exerciseForAction {
                withAnimation {
                    editableExercises.removeAll { $0.id == ex.id }
                }
            }
        }
        
        Button("Cancel", role: .cancel) { }
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
