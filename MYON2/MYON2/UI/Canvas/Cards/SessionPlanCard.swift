import SwiftUI

public struct SessionPlanCard: View {
    private let model: CanvasCardModel
    public init(model: CanvasCardModel) { self.model = model }
    public var body: some View {
        CardContainer(status: model.status) {
            VStack(alignment: .leading, spacing: Space.sm) {
                CardHeader(title: model.title ?? "Session Plan", subtitle: model.subtitle, lane: model.lane, status: model.status, timestamp: Date())
                if case .sessionPlan(let exercises) = model.data {
                    VStack(alignment: .leading, spacing: Space.xs) {
                        ForEach(exercises) { ex in
                            HStack {
                                StatusTag("x\(ex.sets)", kind: .info)
                                MyonText(ex.name, style: .body)
                                Spacer()
                                Icon("chevron.right", size: .sm, color: ColorsToken.Text.secondary)
                            }
                        }
                    }
                }
            }
        }
    }
}


