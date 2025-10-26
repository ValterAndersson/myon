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
                                MyonText(q.label, style: .subheadline)
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
                                    // List selection - clicking submits immediately
                                    VStack(spacing: Space.xs) {
                                        ForEach(opts, id: \.self) { opt in
                                            Button(action: {
                                                answers[q.id] = opt
                                                // Auto-submit for single selection
                                                print("[ClarifyQuestionsCard] Selected option: \(opt) for question: \(q.id)")
                                                submitAnswer()
                                            }) {
                                                HStack {
                                                    MyonText(opt, style: .body)
                                                        .foregroundColor(answers[q.id] == opt ? ColorsToken.Text.inverse : ColorsToken.Text.primary)
                                                    Spacer()
                                                    if answers[q.id] == opt {
                                                        Image(systemName: "checkmark")
                                                            .foregroundColor(ColorsToken.Text.inverse)
                                                    }
                                                }
                                                .padding(InsetsToken.symmetric(vertical: Space.sm, horizontal: Space.md))
                                                .background(answers[q.id] == opt ? ColorsToken.Brand.primary : ColorsToken.Background.secondary)
                                                .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.medium))
                                            }
                                            .buttonStyle(PlainButtonStyle())
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
                
                // Show action buttons only for text questions or if no selection made
                if shouldShowActionButtons() {
                    CardActionBar(actions: model.actions, onAction: { action in 
                        if action.kind == "submit" {
                            submitAnswer()
                        } else if action.kind == "dismiss" || action.kind == "skip" {
                            skipQuestion()
                        } else {
                            handleAction(action, model)
                        }
                    })
                }
            }
        }
    }
    
    private func shouldShowActionButtons() -> Bool {
        guard case .clarifyQuestions(let qs) = model.data else { return false }
        // Only show buttons for text input questions
        // Choice questions auto-submit on selection
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


