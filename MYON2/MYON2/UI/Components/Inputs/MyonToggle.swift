import SwiftUI

public struct MyonToggle: View {
    private let title: String
    @Binding private var isOn: Bool
    private let subtitle: String?

    public init(_ title: String, isOn: Binding<Bool>, subtitle: String? = nil) {
        self.title = title
        self._isOn = isOn
        self.subtitle = subtitle
    }

    public var body: some View {
        Toggle(isOn: $isOn) {
            VStack(alignment: .leading, spacing: Space.xxs) {
                MyonText(title, style: .body)
                if let subtitle { MyonText(subtitle, style: .footnote, color: ColorsToken.Text.secondary) }
            }
        }
        .toggleStyle(SwitchToggleStyle(tint: ColorsToken.Brand.primary))
        .padding(.vertical, Space.xs)
    }
}

#if DEBUG
struct MyonToggle_Previews: PreviewProvider {
    static var previews: some View {
        StatefulPreviewWrapper(true) { binding in
            VStack(alignment: .leading, spacing: Space.md) {
                MyonToggle("Enable analytics", isOn: binding)
                MyonToggle("Enable sensors", isOn: binding, subtitle: "Use Apple Watch for HR")
            }
            .padding(InsetsToken.screen)
        }
    }
}
#endif


