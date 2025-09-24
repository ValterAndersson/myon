import SwiftUI

public struct MyonSlider: View {
    private let title: String
    @Binding private var value: Double
    private let range: ClosedRange<Double>
    private let step: Double
    private let formatter: (Double) -> String

    public init(_ title: String, value: Binding<Double>, in range: ClosedRange<Double>, step: Double = 1, formatter: @escaping (Double) -> String = { String(Int($0)) }) {
        self.title = title
        self._value = value
        self.range = range
        self.step = step
        self.formatter = formatter
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: Space.xs) {
            HStack {
                MyonText(title, style: .subheadline, color: ColorsToken.Text.secondary)
                Spacer()
                MyonText(formatter(value), style: .subheadline)
            }
            Slider(value: $value, in: range, step: step)
                .tint(ColorsToken.Brand.primary)
        }
    }
}

#if DEBUG
struct MyonSlider_Previews: PreviewProvider {
    static var previews: some View {
        StatefulPreviewWrapper(8.0) { binding in
            MyonSlider("RIR", value: binding, in: 0...5, step: 1) { String(Int($0)) }
                .padding(InsetsToken.screen)
        }
    }
}
#endif


