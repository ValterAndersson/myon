import SwiftUI

public enum PovverButtonStyleKind {
    case primary
    case secondary
    case ghost
    case destructive
}

public struct PovverButton: View {
    private let title: String
    private let style: PovverButtonStyleKind
    private let leadingIcon: Image?
    private let trailingIcon: Image?
    private let action: () -> Void
    @Environment(\.povverTheme) private var theme
    @Environment(\.isEnabled) private var isEnabled

    public init(_ title: String, style: PovverButtonStyleKind = .primary, leadingIcon: Image? = nil, trailingIcon: Image? = nil, action: @escaping () -> Void) {
        self.title = title
        self.style = style
        self.leadingIcon = leadingIcon
        self.trailingIcon = trailingIcon
        self.action = action
    }

    public var body: some View {
        Button(action: action) {
            HStack(spacing: Space.sm) {
                if let leadingIcon { leadingIcon.resizable().aspectRatio(contentMode: .fit).frame(width: IconSizeToken.md, height: IconSizeToken.md) }
                SwiftUI.Text(title).font(TypographyToken.button)
                if let trailingIcon { trailingIcon.resizable().aspectRatio(contentMode: .fit).frame(width: IconSizeToken.md, height: IconSizeToken.md) }
            }
            .frame(maxWidth: .infinity)
            .frame(height: theme.buttonHeight)
            .contentShape(Rectangle())
            .frame(minHeight: theme.hitTargetMin)
        }
        .buttonStyle(MappedButtonStyle(kind: style, enabled: isEnabled))
        .accessibilityAddTraits(.isButton)
    }
}

private struct MappedButtonStyle: ButtonStyle {
    let kind: PovverButtonStyleKind
    let enabled: Bool
    func makeBody(configuration: Configuration) -> some View {
        let pressed = configuration.isPressed
        return configuration.label
            .padding(.horizontal, Space.lg)
            .background(backgroundColor(pressed: pressed))
            .foregroundColor(foregroundColor())
            .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.medium, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: CornerRadiusToken.medium, style: .continuous)
                    .strokeBorder(borderColor(pressed: pressed), lineWidth: StrokeWidthToken.thin)
            )
            .overlay(
                RoundedRectangle(cornerRadius: CornerRadiusToken.medium, style: .continuous)
                    .stroke(ColorsToken.Brand.accent700.opacity(0.6), lineWidth: 2)
                    .opacity(isFocused() ? 1 : 0)
            )
            .opacity(enabled ? 1.0 : 0.6)
            .animation(.easeInOut(duration: MotionToken.fast), value: pressed)
    }

    private func isFocused() -> Bool { false }

    private func foregroundColor() -> Color {
        switch kind {
        case .primary: return ColorsToken.Text.inverse
        case .secondary: return ColorsToken.Text.primary
        case .ghost: return ColorsToken.Text.primary
        case .destructive: return ColorsToken.Text.inverse
        }
    }

    private func backgroundColor(pressed: Bool) -> Color {
        let pressOverlay: Double = pressed ? 0.08 : 0
        switch kind {
        case .primary: return ColorsToken.Brand.primary.opacity(1 - pressOverlay)
        case .secondary: return ColorsToken.Surface.default.opacity(1 - pressOverlay)
        case .ghost: return ColorsToken.Surface.default.opacity(pressOverlay)
        case .destructive: return ColorsToken.State.error.opacity(1 - pressOverlay)
        }
    }

    private func borderColor(pressed: Bool) -> Color {
        let base = ColorsToken.Border.default
        switch kind {
        case .primary: return base.opacity(0)
        case .secondary: return base.opacity(1)
        case .ghost: return base.opacity(pressed ? 1 : 0)
        case .destructive: return base.opacity(0)
        }
    }
}

#if DEBUG
struct PovverButton_Previews: PreviewProvider {
    static var previews: some View {
        VStack(spacing: Space.md) {
            PovverButton("Primary") {}
            PovverButton("Secondary", style: .secondary) {}
            PovverButton("Ghost", style: .ghost) {}
            PovverButton("Delete", style: .destructive) {}
        }
        .padding(InsetsToken.screen)
    }
}
#endif


