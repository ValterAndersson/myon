import SwiftUI

public struct ListCardWithExpandableOptions: View {
    private let model: CanvasCardModel
    private let options: [ListOption]
    private let onSelect: (String) -> Void
    public init(model: CanvasCardModel, options: [ListOption], onSelect: @escaping (String) -> Void = { _ in }) {
        self.model = model
        self.options = options
        self.onSelect = onSelect
    }
    @Environment(\.cardActionHandler) private var handleAction

    public var body: some View {
        CardContainer(status: model.status) {
            VStack(alignment: .leading, spacing: Space.md) {
                CardHeader(title: model.title, subtitle: model.subtitle, lane: model.lane, status: model.status, timestamp: Date(), menuActions: model.menuItems, onAction: { action in handleAction(action, model) })
                if case .programDay(let title, _) = model.data {
                    MyonText(title, style: .headline)
                }
                VStack(spacing: Space.sm) {
                    ForEach(options) { opt in
                        Button(action: { onSelect(opt.id) }) {
                            ListRow(title: opt.title, subtitle: opt.subtitle) {
                                if let icon = opt.iconSystemName { Icon(icon, size: .md, color: ColorsToken.Text.primary) }
                            } trailing: {
                                Icon("chevron.right", size: .md, color: ColorsToken.Text.secondary)
                            }
                        }
                        .buttonStyle(PlainButtonStyle())
                    }
                }
                .fixedSize(horizontal: false, vertical: true)
                if !model.actions.isEmpty { CardActionBar(actions: model.actions, onAction: { action in handleAction(action, model) }) }
            }
        }
    }
}

#if DEBUG
struct ListCardWithExpandableOptions_Previews: PreviewProvider {
    static var previews: some View {
        let card = CanvasCardModel(type: .session_plan, title: "Upper Body Focus", data: .programDay(title: "Day 1", exercises: [
            PlanExercise(name: "Bench Press", sets: 4),
            PlanExercise(name: "Pull Ups", sets: 3)
        ]))
        let opts = [
            ListOption(title: "Bench Press", subtitle: "4 sets of 8-10 reps", iconSystemName: "dumbbell"),
            ListOption(title: "Pull Ups", subtitle: "3 sets to failure", iconSystemName: "figure.pullup"),
        ]
        ScrollView { ListCardWithExpandableOptions(model: card, options: opts).padding(InsetsToken.screen) }
    }
}
#endif


