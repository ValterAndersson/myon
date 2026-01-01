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
            PlanExercise(name: "Bench Press", sets: [
                PlanSet(type: .warmup, reps: 10, weight: 30),
                PlanSet(type: .warmup, reps: 6, weight: 50),
                PlanSet(type: .working, reps: 8, weight: 70, rir: 3),
                PlanSet(type: .working, reps: 8, weight: 70, rir: 2)
            ], primaryMuscles: ["chest"]),
            PlanExercise(name: "Lat Pulldown", sets: [
                PlanSet(type: .working, reps: 10, weight: 50, rir: 2),
                PlanSet(type: .working, reps: 10, weight: 50, rir: 2),
                PlanSet(type: .working, reps: 10, weight: 50, rir: 1)
            ], primaryMuscles: ["lats"])
        ]))
        ScrollView { WorkoutRailView(session: session).padding(InsetsToken.screen) }
    }
}
#endif
