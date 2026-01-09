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

// MARK: - v1.1 Premium Visual System Button Style
private struct MappedButtonStyle: ButtonStyle {
    let kind: PovverButtonStyleKind
    let enabled: Bool
    
    func makeBody(configuration: Configuration) -> some View {
        let pressed = configuration.isPressed
        return configuration.label
            .padding(.horizontal, Space.lg)
            .background(backgroundColor(pressed: pressed, enabled: enabled))
            .foregroundColor(foregroundColor(enabled: enabled))
            .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.radiusControl, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: CornerRadiusToken.radiusControl, style: .continuous)
                    .strokeBorder(borderColor(pressed: pressed, enabled: enabled), lineWidth: StrokeWidthToken.hairline)
            )
            .opacity(enabled ? 1.0 : 1.0) // Disabled state handled via colors, not opacity
            .animation(.easeInOut(duration: MotionToken.fast), value: pressed)
    }

    private func foregroundColor(enabled: Bool) -> Color {
        guard enabled else { return .textTertiary }
        switch kind {
        case .primary: return .textInverse
        case .secondary: return .textPrimary
        case .ghost: return .textPrimary
        case .destructive: return .textInverse
        }
    }

    private func backgroundColor(pressed: Bool, enabled: Bool) -> Color {
        guard enabled else { return .separator }
        switch kind {
        case .primary: 
            return pressed ? .accentPressed : .accent
        case .secondary: 
            return pressed ? .surfaceElevated : .surface
        case .ghost: 
            return pressed ? .surfaceElevated : .clear
        case .destructive: 
            return pressed ? .destructive.opacity(0.85) : .destructive
        }
    }

    private func borderColor(pressed: Bool, enabled: Bool) -> Color {
        guard enabled else { return .separator }
        switch kind {
        case .primary: return .clear
        case .secondary: return .separator
        case .ghost: return pressed ? .separator : .clear
        case .destructive: return .clear
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


