import SwiftUI

public enum IconSize { case sm, md, lg }

public struct Icon: View {
    private let systemName: String
    private let size: IconSize
    private let color: Color

    public init(_ systemName: String, size: IconSize = .md, color: Color = ColorsToken.Text.primary) {
        self.systemName = systemName
        self.size = size
        self.color = color
    }

    public var body: some View {
        Image(systemName: systemName)
            .resizable()
            .scaledToFit()
            .frame(width: dimension, height: dimension)
            .foregroundColor(color)
    }

    private var dimension: CGFloat {
        switch size {
        case .sm: return IconSizeToken.sm
        case .md: return IconSizeToken.md
        case .lg: return IconSizeToken.lg
        }
    }
}

#if DEBUG
struct Icon_Previews: PreviewProvider {
    static var previews: some View {
        HStack(spacing: Space.md) {
            Icon("star.fill", size: .sm)
            Icon("star.fill", size: .md)
            Icon("star.fill", size: .lg)
        }
        .padding(InsetsToken.screen)
    }
}
#endif


