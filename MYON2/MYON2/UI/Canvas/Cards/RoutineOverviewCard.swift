import SwiftUI

public struct RoutineOverviewCard: View {
    private let model: CanvasCardModel
    public init(model: CanvasCardModel) { self.model = model }
    public var body: some View {
        CardContainer(status: model.status) {
            VStack(alignment: .leading, spacing: Space.md) {
                CardHeader(title: model.title ?? "Your Program", subtitle: model.subtitle, lane: model.lane, status: model.status, timestamp: Date(), menuActions: model.menuItems, onAction: { action in
                    let handler = Environment(\.cardActionHandler).wrappedValue
                    handler(action, model)
                })
                if case .routineOverview(let split, let days, let notes) = model.data {
                    HStack(spacing: Space.lg) {
                        VStack(alignment: .leading, spacing: Space.xs) {
                            MyonText("Split", style: .footnote, color: ColorsToken.Text.secondary)
                            MyonText(split, style: .headline)
                        }
                        VStack(alignment: .leading, spacing: Space.xs) {
                            MyonText("Days", style: .footnote, color: ColorsToken.Text.secondary)
                            MyonText(String(days), style: .headline)
                        }
                        Spacer()
                    }
                    if let notes { MyonText(notes, style: .body, color: ColorsToken.Text.secondary) }
                }
                if !model.actions.isEmpty { CardActionBar(actions: model.actions, onAction: { action in
                    let handler = Environment(\.cardActionHandler).wrappedValue
                    handler(action, model)
                }) }
            }
        }
    }
}


