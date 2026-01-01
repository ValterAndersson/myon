import SwiftUI

public struct QuickActionCard: View {
    private let title: String
    private let icon: String
    private let action: () -> Void

    public init(title: String, icon: String, action: @escaping () -> Void) {
        self.title = title
        self.icon = icon
        self.action = action
    }

    public var body: some View {
        Button(action: action) {
            SurfaceCard(elevation: ShadowsToken.level2, padding: InsetsToken.all(Space.md), backgroundColor: .white) {
                HStack(spacing: Space.md) {
                    Image(systemName: icon)
                        .resizable().scaledToFit()
                        .frame(width: IconSizeToken.md, height: IconSizeToken.md)
                        .foregroundColor(ColorsToken.Text.primary)
                    PovverText(title, style: .subheadline)
                        .lineLimit(2)
                    Spacer()
                    Icon("chevron.right", size: .md, color: ColorsToken.Text.secondary)
                }
                .frame(height: 64)
            }
        }
        .buttonStyle(PlainButtonStyle())
    }
}

#if DEBUG
struct QuickActionCard_Previews: PreviewProvider {
    static var previews: some View {
        VStack(spacing: Space.md) {
            QuickActionCard(title: "Start exercise", icon: "play.fill", action: {})
            QuickActionCard(title: "Analyze my progress", icon: "chart.bar", action: {})
        }
        .padding(InsetsToken.screen)
    }
}
#endif


