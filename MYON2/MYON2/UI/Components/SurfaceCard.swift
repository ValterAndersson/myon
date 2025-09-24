import SwiftUI

public struct SurfaceCard<Content: View>: View {
    let elevation: ShadowStyle
    let padding: EdgeInsets
    let content: Content
    @Environment(\.myonTheme) private var theme
    let backgroundColor: Color

    public init(elevation: ShadowStyle = ShadowsToken.level1, padding: EdgeInsets = InsetsToken.all(Space.lg), backgroundColor: Color = ColorsToken.Surface.card, @ViewBuilder content: () -> Content) {
        self.elevation = elevation
        self.padding = padding
        self.content = content()
        self.backgroundColor = backgroundColor
    }

    public var body: some View {
        content
            .padding(padding)
            .background(backgroundColor)
            .clipShape(RoundedRectangle(cornerRadius: theme.cornerRadiusLarge, style: .continuous))
            .shadowStyle(elevation)
            .overlay(
                RoundedRectangle(cornerRadius: theme.cornerRadiusLarge, style: .continuous)
                    .stroke(ColorsToken.Border.subtle, lineWidth: StrokeWidthToken.hairline)
            )
    }
}

#if DEBUG
struct SurfaceCard_Previews: PreviewProvider {
    static var previews: some View {
        SurfaceCard {
            VStack(alignment: .leading, spacing: Space.sm) {
                MyonText("Surface Card", style: .headline)
                MyonText("Secondary text for context", style: .subheadline, color: ColorsToken.Text.secondary)
            }
        }
        .padding(InsetsToken.screen)
    }
}
#endif


