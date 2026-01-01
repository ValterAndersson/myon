import SwiftUI

public struct ProposalGroupHeader: View {
    private let model: CanvasCardModel
    private let onAction: (CardAction) -> Void
    public init(model: CanvasCardModel, onAction: @escaping (CardAction) -> Void) {
        self.model = model
        self.onAction = onAction
    }

    public var body: some View {
        CardContainer(status: model.status) {
            VStack(alignment: .leading, spacing: Space.sm) {
                CardHeader(title: model.title, subtitle: model.subtitle, lane: model.lane, status: model.status, timestamp: Date(), menuActions: model.menuItems, onAction: onAction)
                CardActionBar(actions: model.actions, onAction: onAction)
            }
        }
    }
}


