import SwiftUI

public struct SessionPlanCard: View {
    private let model: CanvasCardModel
    @State private var editableExercises: [PlanExercise] = []
    @State private var expandedExerciseId: String? = nil
    @State private var activeMenu: MenuTarget? = nil
    @State private var menuAnchor: CGPoint = .zero
    @State private var exerciseForDetail: PlanExercise? = nil
    @Environment(\.cardActionHandler) private var handleAction
    
    private enum MenuTarget: Equatable {
        case card
        case exercise(String)
    }
    
    public init(model: CanvasCardModel) {
        self.model = model
    }
    
    public var body: some View {
        CardContainer(status: model.status) {
            VStack(alignment: .leading, spacing: Space.sm) {
                cardHeader
                
                VStack(alignment: .leading, spacing: Space.xs) {
                    ForEach(editableExercises.indices, id: \.self) { index in
                        exerciseRow(exercise: editableExercises[index], index: index)
                    }
                }
                
                if model.status == .proposed {
                    acceptButton
                }
            }
        }
        .overlay { menuOverlay }
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
    
    // MARK: - Menu Overlay (on top of everything)
    
    @ViewBuilder
    private var menuOverlay: some View {
        if activeMenu != nil {
            GeometryReader { geo in
                Color.black.opacity(0.001)
                    .onTapGesture { activeMenu = nil }
                
                VStack(alignment: .leading, spacing: 0) {
                    if case .card = activeMenu {
                        cardMenuContent
                    } else if case .exercise(let id) = activeMenu,
                              let ex = editableExercises.first(where: { $0.id == id }) {
                        exerciseMenuContent(ex)
                    }
                }
                .background(ColorsToken.Surface.card)
                .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.medium))
                .shadow(color: .black.opacity(0.12), radius: 12, x: 0, y: 4)
                .overlay(RoundedRectangle(cornerRadius: CornerRadiusToken.medium).stroke(ColorsToken.Border.subtle, lineWidth: 0.5))
                .frame(width: 200)
                .position(x: min(max(menuAnchor.x, 110), geo.size.width - 110), y: menuAnchor.y + 80)
            }
        }
    }
    
    private var cardMenuContent: some View {
        VStack(alignment: .leading, spacing: 0) {
            menuItem("Accept Plan", icon: "checkmark.circle") {
                let action = CardAction(kind: "accept_plan", label: "Accept", style: .primary, payload: serializePlan())
                handleAction(action, model)
            }
            Divider()
            menuItem("Make Shorter", icon: "minus.circle") {
                fireAdjustment("Make this session shorter - reduce total sets or exercises")
            }
            Divider()
            menuItem("Make Harder", icon: "flame") {
                fireAdjustment("Make this session more challenging - increase intensity or volume")
            }
            Divider()
            menuItem("Regenerate", icon: "arrow.triangle.2.circlepath") {
                fireAdjustment("Regenerate this workout plan with different exercises")
            }
            Divider()
            menuItem("Dismiss", icon: "xmark.circle", isDestructive: true) {
                let action = CardAction(kind: "dismiss", label: "Dismiss", style: .destructive)
                handleAction(action, model)
            }
        }
    }
    
    private func exerciseMenuContent(_ exercise: PlanExercise) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            menuItem("Learn About Exercise", icon: "book") {
                exerciseForDetail = exercise
            }
            Divider()
            menuItem("Swap (Same Muscles)", icon: "arrow.left.arrow.right") {
                fireSwap(exercise: exercise, reason: "same_muscles")
            }
            Divider()
            menuItem("Swap (Same Equipment)", icon: "dumbbell") {
                fireSwap(exercise: exercise, reason: "same_equipment")
            }
            Divider()
            menuItem("Swap (Ask AI)", icon: "sparkles") {
                fireSwap(exercise: exercise, reason: "ai_suggestion")
            }
            Divider()
            menuItem("Remove", icon: "trash", isDestructive: true) {
                withAnimation { editableExercises.removeAll { $0.id == exercise.id } }
            }
        }
    }
    
    private func menuItem(_ title: String, icon: String, isDestructive: Bool = false, action: @escaping () -> Void) -> some View {
        Button {
            activeMenu = nil
            action()
        } label: {
            HStack(spacing: Space.sm) {
                Image(systemName: icon)
                    .font(.system(size: 14))
                    .foregroundColor(isDestructive ? ColorsToken.State.error : ColorsToken.Text.secondary)
                    .frame(width: 20)
                Text(title)
                    .font(.system(size: 14))
                    .foregroundColor(isDestructive ? ColorsToken.State.error : ColorsToken.Text.primary)
                Spacer()
            }
            .padding(.horizontal, Space.md)
            .padding(.vertical, 10)
            .contentShape(Rectangle())
        }
        .buttonStyle(PlainButtonStyle())
    }
    
    // MARK: - Card Header
    
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
            GeometryReader { geo in
                Button {
                    menuAnchor = CGPoint(x: geo.frame(in: .named("card")).midX, y: geo.frame(in: .named("card")).minY)
                    activeMenu = .card
                } label: {
                    Image(systemName: "ellipsis")
                        .font(.system(size: 16, weight: .medium))
                        .foregroundColor(ColorsToken.Text.secondary)
                        .frame(width: 32, height: 32)
                        .background(ColorsToken.Background.secondary.opacity(0.6))
                        .clipShape(Circle())
                }
                .buttonStyle(PlainButtonStyle())
            }
            .frame(width: 32, height: 32)
        }
        .coordinateSpace(name: "card")
    }
    
    // MARK: - Exercise Row
    
    private func exerciseRow(exercise: PlanExercise, index: Int) -> some View {
        let isExpanded = expandedExerciseId == exercise.id
        
        return VStack(alignment: .leading, spacing: 0) {
            HStack {
                Button {
                    withAnimation(.easeInOut(duration: 0.2)) {
                        expandedExerciseId = isExpanded ? nil : exercise.id
                    }
                } label: {
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
                
                GeometryReader { geo in
                    Button {
                        menuAnchor = CGPoint(x: geo.frame(in: .named("card")).midX, y: geo.frame(in: .named("card")).minY)
                        activeMenu = .exercise(exercise.id)
                    } label: {
                        Image(systemName: "ellipsis")
                            .font(.system(size: 14))
                            .foregroundColor(ColorsToken.Text.secondary)
                            .frame(width: 28, height: 28)
                            .background(Color.clear)
                            .clipShape(Circle())
                    }
                    .buttonStyle(PlainButtonStyle())
                }
                .frame(width: 28, height: 28)
            }
            .padding(.vertical, Space.xs)
            
            if isExpanded {
                expandedContent(index: index)
                    .transition(.opacity.combined(with: .move(edge: .top)))
            }
        }
    }
    
    // MARK: - Expanded Content
    
    @ViewBuilder
    private func expandedContent(index: Int) -> some View {
        VStack(alignment: .leading, spacing: Space.sm) {
            HStack(spacing: Space.lg) {
                VStack(alignment: .leading, spacing: 2) {
                    MyonText("Sets", style: .caption).foregroundColor(ColorsToken.Text.secondary)
                    stepper(value: Binding(get: { editableExercises[index].sets }, set: { editableExercises[index].sets = $0 }), range: 1...10)
                }
                VStack(alignment: .leading, spacing: 2) {
                    MyonText("Reps", style: .caption).foregroundColor(ColorsToken.Text.secondary)
                    stepper(value: Binding(get: { editableExercises[index].reps }, set: { editableExercises[index].reps = $0 }), range: 1...30)
                }
                VStack(alignment: .leading, spacing: 2) {
                    MyonText("RIR", style: .caption).foregroundColor(ColorsToken.Text.secondary)
                    stepper(value: Binding(get: { editableExercises[index].rir ?? 2 }, set: { editableExercises[index].rir = $0 }), range: 0...5)
                }
                Spacer()
            }
            
            HStack(spacing: Space.sm) {
                MyonText("Weight", style: .caption).foregroundColor(ColorsToken.Text.secondary)
                TextField("--", value: Binding(get: { editableExercises[index].weight }, set: { editableExercises[index].weight = $0 }), format: .number)
                    .keyboardType(.decimalPad).textFieldStyle(.plain).frame(width: 60)
                    .padding(.horizontal, Space.sm).padding(.vertical, 4)
                    .background(ColorsToken.Background.secondary)
                    .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.small))
                MyonText("kg", style: .caption).foregroundColor(ColorsToken.Text.secondary)
            }
            
            if let note = editableExercises[index].coachNote, !note.isEmpty {
                HStack(spacing: Space.xs) {
                    Image(systemName: "text.bubble").font(.system(size: 12)).foregroundColor(ColorsToken.Brand.primary)
                    MyonText(note, style: .caption).foregroundColor(ColorsToken.Text.secondary)
                }
            }
            
            if let muscles = editableExercises[index].primaryMuscles, !muscles.isEmpty {
                HStack(spacing: Space.xs) {
                    Image(systemName: "figure.strengthtraining.traditional").font(.system(size: 12)).foregroundColor(ColorsToken.Text.secondary)
                    MyonText(muscles.joined(separator: ", "), style: .caption).foregroundColor(ColorsToken.Text.secondary)
                }
            }
        }
        .padding(.leading, 28).padding(.bottom, Space.sm)
    }
    
    private func stepper(value: Binding<Int>, range: ClosedRange<Int>) -> some View {
        HStack(spacing: 0) {
            Button { if value.wrappedValue > range.lowerBound { value.wrappedValue -= 1 } } label: {
                Image(systemName: "minus").font(.system(size: 12, weight: .medium))
                    .foregroundColor(value.wrappedValue <= range.lowerBound ? ColorsToken.Text.secondary.opacity(0.3) : ColorsToken.Text.primary)
                    .frame(width: 28, height: 28)
            }.disabled(value.wrappedValue <= range.lowerBound)
            
            Text("\(value.wrappedValue)").font(.system(size: 14, weight: .medium)).foregroundColor(ColorsToken.Text.primary).frame(width: 32)
            
            Button { if value.wrappedValue < range.upperBound { value.wrappedValue += 1 } } label: {
                Image(systemName: "plus").font(.system(size: 12, weight: .medium))
                    .foregroundColor(value.wrappedValue >= range.upperBound ? ColorsToken.Text.secondary.opacity(0.3) : ColorsToken.Text.primary)
                    .frame(width: 28, height: 28)
            }.disabled(value.wrappedValue >= range.upperBound)
        }
        .background(ColorsToken.Background.secondary)
        .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.small))
    }
    
    private var acceptButton: some View {
        Button {
            let action = CardAction(kind: "accept_plan", label: "Accept", style: .primary, payload: serializePlan())
            handleAction(action, model)
        } label: {
            HStack { Image(systemName: "checkmark"); MyonText("Accept Plan", style: .body) }
                .frame(maxWidth: .infinity).padding(.vertical, Space.sm)
                .background(ColorsToken.Brand.primary).foregroundColor(.white)
                .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.medium))
        }
        .buttonStyle(PlainButtonStyle()).padding(.top, Space.sm)
    }
    
    // MARK: - Actions
    
    private func fireAdjustment(_ instruction: String) {
        let action = CardAction(kind: "adjust_plan", label: instruction, payload: ["instruction": instruction, "current_plan": serializePlanForAgent()])
        handleAction(action, model)
    }
    
    private func fireSwap(exercise: PlanExercise, reason: String) {
        let muscles = exercise.primaryMuscles?.joined(separator: ", ") ?? "unknown"
        let equipment = exercise.equipment ?? "unknown"
        let instruction: String
        switch reason {
        case "same_muscles": instruction = "Swap \(exercise.name) for another exercise targeting \(muscles)"
        case "same_equipment": instruction = "Swap \(exercise.name) for another \(equipment) exercise"
        case "ai_suggestion": instruction = "Suggest a replacement for \(exercise.name) that fits this workout"
        default: instruction = "Swap \(exercise.name)"
        }
        let action = CardAction(kind: "swap_exercise", label: "Swap", payload: ["instruction": instruction, "exercise_id": exercise.exerciseId ?? "", "exercise_name": exercise.name, "swap_reason": reason, "current_plan": serializePlanForAgent()])
        handleAction(action, model)
    }
    
    private func serializePlan() -> [String: String] {
        guard let data = try? JSONEncoder().encode(editableExercises), let json = String(data: data, encoding: .utf8) else { return [:] }
        return ["exercises_json": json]
    }
    
    private func serializePlanForAgent() -> String {
        editableExercises.enumerated().map { i, ex in
            var line = "\(i + 1). \(ex.name) - \(ex.sets) sets × \(ex.reps) reps"
            if let rir = ex.rir { line += " @ RIR \(rir)" }
            if let weight = ex.weight { line += ", \(Int(weight))kg" }
            return line
        }.joined(separator: "\n")
    }
}
