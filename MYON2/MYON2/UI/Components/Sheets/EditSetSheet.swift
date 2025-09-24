import SwiftUI

public struct EditSetSheet: View {
    @State private var sets: Int
    @State private var reps: Int
    @State private var weight: Double
    private let onSubmit: (Int, Int, Double) -> Void

    public init(initialSets: Int = 3, initialReps: Int = 10, initialWeight: Double = 0, onSubmit: @escaping (Int, Int, Double) -> Void) {
        self._sets = State(initialValue: initialSets)
        self._reps = State(initialValue: initialReps)
        self._weight = State(initialValue: initialWeight)
        self.onSubmit = onSubmit
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: Space.lg) {
            MyonText("Edit target", style: .headline)
            HStack {
                MyonText("Sets", style: .subheadline, color: ColorsToken.Text.secondary)
                Stepper(value: $sets, in: 1...10) { MyonText(String(sets), style: .headline) }
            }
            HStack {
                MyonText("Reps", style: .subheadline, color: ColorsToken.Text.secondary)
                Stepper(value: $reps, in: 1...30) { MyonText(String(reps), style: .headline) }
            }
            HStack {
                MyonText("Weight", style: .subheadline, color: ColorsToken.Text.secondary)
                Slider(value: $weight, in: 0...300, step: 2.5).tint(ColorsToken.Brand.primary)
                MyonText(String(format: "%.1f kg", weight), style: .headline)
            }
            MyonButton("Apply", style: .primary) { onSubmit(sets, reps, weight) }
        }
        .padding(InsetsToken.screen)
    }
}


