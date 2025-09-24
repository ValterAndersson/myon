import SwiftUI

public struct ClarifyQuestionsCard: View {
    private let model: CanvasCardModel
    @State private var answers: [String: String] = [:]
    public init(model: CanvasCardModel) { self.model = model }
    @Environment(\.cardActionHandler) private var handleAction

    public var body: some View {
        CardContainer(status: model.status) {
            VStack(alignment: .leading, spacing: Space.md) {
                CardHeader(title: model.title ?? "A few questions", subtitle: model.subtitle, lane: model.lane, status: model.status, timestamp: Date(), menuActions: model.menuItems, onAction: { action in handleAction(action, model) })
                if case .clarifyQuestions(let qs) = model.data {
                    VStack(alignment: .leading, spacing: Space.md) {
                        ForEach(qs) { q in
                            VStack(alignment: .leading, spacing: Space.xs) {
                                MyonText(q.label, style: .subheadline)
                                if q.type == .text {
                                    TextField("", text: Binding(get: { answers[q.id] ?? "" }, set: { answers[q.id] = $0 }))
                                        .textInputAutocapitalization(.sentences)
                                        .padding(InsetsToken.symmetric(vertical: Space.sm, horizontal: Space.md))
                                        .background(ColorsToken.Background.secondary)
                                        .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.medium, style: .continuous))
                                } else if let opts = q.options {
                                    ScrollView(.horizontal, showsIndicators: false) {
                                        HStack(spacing: Space.sm) {
                                            ForEach(opts, id: \.self) { opt in
                                                Button(opt) { answers[q.id] = opt }
                                                    .buttonStyle(.bordered)
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
                CardActionBar(actions: model.actions, onAction: { action in handleAction(action, model) })
            }
        }
    }
}


