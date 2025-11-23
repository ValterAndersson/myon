import SwiftUI

public struct ClarifyQuestionsCard: View {
    private let model: CanvasCardModel
    @State private var answers: [String: String] = [:]
    @State private var selectedOptions: Set<String> = []
    public init(model: CanvasCardModel) { self.model = model }
    @Environment(\.cardActionHandler) private var handleAction

    public var body: some View {
        CardContainer(status: model.status) {
            VStack(alignment: .leading, spacing: Space.md) {
                CardHeader(title: model.title ?? "A few questions", subtitle: model.subtitle, lane: model.lane, status: model.status, timestamp: Date(), menuActions: model.menuItems, onAction: { action in handleAction(action, model) })
                if case .clarifyQuestions(let qs) = model.data {
                    VStack(alignment: .leading, spacing: Space.md) {
                        ForEach(qs) { q in
                            VStack(alignment: .leading, spacing: Space.sm) {
                                MyonText(q.text, style: .subheadline)
                                    .foregroundColor(ColorsToken.Text.primary)
                                
                                if q.type == .text {
                                    // Text input with submit/skip
                                    TextField("Type your answer...", text: Binding(
                                        get: { answers[q.id] ?? "" },
                                        set: { answers[q.id] = $0 }
                                    ))
                                    .textInputAutocapitalization(.sentences)
                                    .padding(InsetsToken.symmetric(vertical: Space.sm, horizontal: Space.md))
                                    .background(ColorsToken.Background.secondary)
                                    .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.medium, style: .continuous))
                                    
                                } else if let opts = q.options {
                                    // List selection - clicking submits immediately for single_choice
                                    VStack(spacing: Space.xs) {
                                        ForEach(opts, id: \.self) { opt in
                                            Button(action: {
                                                if q.type == .multi_choice {
                                                    // Toggle selection for multi-choice
                                                    if selectedOptions.contains(opt) {
                                                        selectedOptions.remove(opt)
                                                    } else {
                                                        selectedOptions.insert(opt)
                                                    }
                                                    answers[q.id] = Array(selectedOptions).joined(separator: ",")
                                                } else {
                                                    // Single choice - auto submit
                                                    answers[q.id] = opt
                                                    print("[ClarifyQuestionsCard] Selected option: \(opt) for question: \(q.id)")
                                                    submitAnswer()
                                                }
                                            }) {
                                                HStack {
                                                    MyonText(opt, style: .body)
                                                        .foregroundColor(isOptionSelected(opt, questionId: q.id) ? ColorsToken.Text.inverse : ColorsToken.Text.primary)
                                                    Spacer()
                                                    if isOptionSelected(opt, questionId: q.id) {
                                                        Image(systemName: q.type == .multi_choice ? "checkmark.square.fill" : "checkmark")
                                                            .foregroundColor(ColorsToken.Text.inverse)
                                                    }
                                                }
                                                .padding(InsetsToken.symmetric(vertical: Space.sm, horizontal: Space.md))
                                                .background(isOptionSelected(opt, questionId: q.id) ? ColorsToken.Brand.primary : ColorsToken.Background.secondary)
                                                .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.medium))
                                            }
                                            .buttonStyle(PlainButtonStyle())
                                        }
                                    }
                                } else if q.type == .yes_no {
                                    // Yes/No buttons - clicking either submits immediately
                                    HStack(spacing: Space.md) {
                                        Button(action: {
                                            answers[q.id] = "yes"
                                            submitAnswer()
                                        }) {
                                            HStack {
                                                Image(systemName: "checkmark")
                                                MyonText("Yes", style: .body)
                                            }
                                            .frame(maxWidth: .infinity)
                                            .padding(InsetsToken.symmetric(vertical: Space.sm, horizontal: Space.md))
                                            .background(Color.green)
                                            .foregroundColor(.white)
                                            .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.medium))
                                        }
                                        .buttonStyle(PlainButtonStyle())
                                        
                                        Button(action: {
                                            answers[q.id] = "no"
                                            submitAnswer()
                                        }) {
                                            HStack {
                                                Image(systemName: "xmark")
                                                MyonText("No", style: .body)
                                            }
                                            .frame(maxWidth: .infinity)
                                            .padding(InsetsToken.symmetric(vertical: Space.sm, horizontal: Space.md))
                                            .background(Color.red)
                                            .foregroundColor(.white)
                                            .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.medium))
                                        }
                                        .buttonStyle(PlainButtonStyle())
                                    }
                                }
                            }
                        }
                    }
                }
                
                // Show action buttons only for text questions or multi-choice
                if shouldShowActionButtons() {
                    HStack(spacing: Space.md) {
                        if hasTextQuestion() {
                            Button(action: skipQuestion) {
                                HStack {
                                    Image(systemName: "arrow.right")
                                    MyonText("Skip", style: .body)
                                }
                                .padding(InsetsToken.symmetric(vertical: Space.sm, horizontal: Space.lg))
                                .background(ColorsToken.Background.secondary)
                                .foregroundColor(ColorsToken.Text.secondary)
                                .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.medium))
                            }
                            .buttonStyle(PlainButtonStyle())
                        }
                        
                        Button(action: submitAnswer) {
                            HStack {
                                Image(systemName: "paperplane.fill")
                                MyonText("Submit", style: .body)
                            }
                            .padding(InsetsToken.symmetric(vertical: Space.sm, horizontal: Space.lg))
                            .background(ColorsToken.Brand.primary)
                            .foregroundColor(.white)
                            .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.medium))
                        }
                        .buttonStyle(PlainButtonStyle())
                    }
                }
            }
        }
    }
    
    private func isOptionSelected(_ option: String, questionId: String) -> Bool {
        if selectedOptions.contains(option) {
            return true
        }
        return answers[questionId] == option
    }
    
    private func shouldShowActionButtons() -> Bool {
        guard case .clarifyQuestions(let qs) = model.data else { return false }
        // Show buttons for text input or multi-choice questions
        return qs.contains { $0.type == .text || $0.type == .multi_choice }
    }
    
    private func hasTextQuestion() -> Bool {
        guard case .clarifyQuestions(let qs) = model.data else { return false }
        return qs.contains { $0.type == .text }
    }
    
    private func submitAnswer() {
        print("[ClarifyQuestionsCard] submitAnswer called with answers: \(answers)")
        
        // Create response action with answers
        var payload: [String: String] = [:]
        // Convert answers dictionary to JSON string for payload
        if let answersData = try? JSONSerialization.data(withJSONObject: answers, options: []),
           let answersJson = String(data: answersData, encoding: .utf8) {
            payload["answers"] = answersJson
            print("[ClarifyQuestionsCard] Sending payload: \(answersJson)")
        }
        
        let submitAction = CardAction(
            kind: "submit",
            label: "Submit",
            style: .primary,
            payload: payload
        )
        print("[ClarifyQuestionsCard] Calling handleAction with submit action")
        handleAction(submitAction, model)
    }
    
    private func skipQuestion() {
        // Send skip signal to agent
        var payload: [String: String] = [:]
        payload["skipped"] = "true"
        payload["message"] = "User decided to skip this question. Move to next step accordingly."
        
        let skipAction = CardAction(
            kind: "skip",
            label: "Skip",
            style: .secondary,
            payload: payload
        )
        handleAction(skipAction, model)
    }
}