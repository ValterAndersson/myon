import SwiftUI

/// Train Tab - Workout execution hub
/// Renders FocusModeWorkoutScreen immediately — no loading gate.
/// The screen itself handles active workout detection and start-view rendering.
struct TrainTabView: View {
    var body: some View {
        FocusModeWorkoutScreen()
    }
}

#if DEBUG
struct TrainTabView_Previews: PreviewProvider {
    static var previews: some View {
        NavigationStack {
            TrainTabView()
        }
    }
}
#endif
