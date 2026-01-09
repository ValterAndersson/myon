import SwiftUI

// MARK: - v1.1 Premium Visual System Surface Card
/// A consistent card container with neutral surface background and hairline border.
/// Default: No shadow (Tier 0). Use .elevated for optional Tier 1 shadow.

public enum SurfaceCardElevation {
    case none       // Tier 0: No shadow (default)
    case elevated   // Tier 1: Subtle shadow for floating panels/docks
    
    var shadow: ShadowStyle? {
        switch self {
        case .none: return nil
        case .elevated: return ShadowsToken.level1
        }
    }
}

public struct SurfaceCard<Content: View>: View {
    let elevation: SurfaceCardElevation
    let padding: EdgeInsets
    let content: Content
    let backgroundColor: Color

    /// Creates a SurfaceCard with v1.1 styling
    /// - Parameters:
    ///   - elevation: .none (default, no shadow) or .elevated (Tier 1 subtle shadow)
    ///   - padding: Card internal padding, default 16pt
    ///   - backgroundColor: Background color, default Color.surface
    ///   - content: Card content
    public init(
        elevation: SurfaceCardElevation = .none,
        padding: EdgeInsets = InsetsToken.all(Space.lg),
        backgroundColor: Color = .surface,
        @ViewBuilder content: () -> Content
    ) {
        self.elevation = elevation
        self.padding = padding
        self.content = content()
        self.backgroundColor = backgroundColor
    }
    
    /// Legacy initializer for backward compatibility
    public init(
        elevation: ShadowStyle,
        padding: EdgeInsets = InsetsToken.all(Space.lg),
        backgroundColor: Color = .surface,
        @ViewBuilder content: () -> Content
    ) {
        // Map old ShadowStyle to new elevation system - treat any shadow as elevated
        self.elevation = .elevated
        self.padding = padding
        self.content = content()
        self.backgroundColor = backgroundColor
    }

    public var body: some View {
        content
            .padding(padding)
            .background(backgroundColor)
            .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.radiusCard, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: CornerRadiusToken.radiusCard, style: .continuous)
                    .stroke(Color.separator, lineWidth: StrokeWidthToken.hairline)
            )
            .if(elevation == .elevated) { view in
                view.shadowStyle(ShadowsToken.level1)
            }
    }
}

// MARK: - View Extension for conditional modifier
private extension View {
    @ViewBuilder
    func `if`<Transform: View>(_ condition: Bool, transform: (Self) -> Transform) -> some View {
        if condition {
            transform(self)
        } else {
            self
        }
    }
}

#if DEBUG
struct SurfaceCard_Previews: PreviewProvider {
    static var previews: some View {
        VStack(spacing: Space.xl) {
            SurfaceCard {
                VStack(alignment: .leading, spacing: Space.sm) {
                    Text("Default (No Shadow)")
                        .textStyle(.sectionHeader)
                        .foregroundColor(.textPrimary)
                    Text("Surface with hairline border, no shadow")
                        .textStyle(.secondary)
                        .foregroundColor(.textSecondary)
                }
            }
            
            SurfaceCard(elevation: .elevated) {
                VStack(alignment: .leading, spacing: Space.sm) {
                    Text("Elevated (Tier 1)")
                        .textStyle(.sectionHeader)
                        .foregroundColor(.textPrimary)
                    Text("For floating panels or docks")
                        .textStyle(.secondary)
                        .foregroundColor(.textSecondary)
                }
            }
        }
        .padding(InsetsToken.screen)
        .background(Color.bg)
    }
}
#endif
