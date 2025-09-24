import SwiftUI

public struct WorkoutRailView: View {
    private let session: CanvasCardModel
    public init(session: CanvasCardModel) { self.session = session }
    public var body: some View {
        VStack(alignment: .leading, spacing: Space.md) {
            SessionPlanCard(model: session)
        }
    }
}

#if DEBUG
struct WorkoutRailView_Previews: PreviewProvider {
    static var previews: some View {
        let session = CanvasCardModel(type: .session_plan, lane: .workout, data: .sessionPlan(exercises: [
            PlanExercise(name: "Bench Press", sets: 4),
            PlanExercise(name: "Lat Pulldown", sets: 4)
        ]))
        ScrollView { WorkoutRailView(session: session).padding(InsetsToken.screen) }
    }
}
#endif


