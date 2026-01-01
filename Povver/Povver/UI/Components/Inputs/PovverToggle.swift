import SwiftUI

public struct PovverToggle: View {
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
                PovverText(title, style: .body)
                if let subtitle { PovverText(subtitle, style: .footnote, color: ColorsToken.Text.secondary) }
            }
        }
        .toggleStyle(SwitchToggleStyle(tint: ColorsToken.Brand.primary))
        .padding(.vertical, Space.xs)
    }
}

#if DEBUG
struct PovverToggle_Previews: PreviewProvider {
    static var previews: some View {
        StatefulPreviewWrapper(true) { binding in
            VStack(alignment: .leading, spacing: Space.md) {
                PovverToggle("Enable analytics", isOn: binding)
                PovverToggle("Enable sensors", isOn: binding, subtitle: "Use Apple Watch for HR")
            }
            .padding(InsetsToken.screen)
        }
    }
}
#endif


