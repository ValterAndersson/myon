import SwiftUI

public struct SuggestionCard: View {
    private let model: CanvasCardModel
    private let onAccept: () -> Void
    private let onReject: () -> Void
    public init(model: CanvasCardModel, onAccept: @escaping () -> Void = {}, onReject: @escaping () -> Void = {}) {
        self.model = model
        self.onAccept = onAccept
        self.onReject = onReject
    }
    public var body: some View {
        CardContainer(status: model.status) {
            VStack(alignment: .leading, spacing: Space.sm) {
                CardHeader(title: model.title, subtitle: model.subtitle, lane: model.lane, status: model.status, timestamp: Date())
                switch model.data {
                case .suggestion(_, let rationale):
                    if let rationale { MyonText(rationale, style: .subheadline, color: ColorsToken.Text.secondary) }
                default: EmptyView()
                }
                HStack(spacing: Space.sm) {
                    MyonButton("Accept", style: .primary, action: onAccept)
                    MyonButton("Reject", style: .secondary, action: onReject)
                }
            }
        }
    }
}


