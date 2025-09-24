import SwiftUI

public struct Avatar: View {
    private let image: Image?
    private let initials: String
    private let size: CGFloat

    public init(image: Image? = nil, initials: String, size: CGFloat = 40) {
        self.image = image
        self.initials = initials
        self.size = size
    }

    public var body: some View {
        ZStack {
            if let image {
                image
                    .resizable()
                    .scaledToFill()
            } else {
                Circle()
                    .fill(ColorsToken.Surface.default)
                SwiftUI.Text(initials)
                    .font(.system(size: max(12, size * 0.4), weight: .semibold))
                    .foregroundColor(ColorsToken.Text.primary)
            }
        }
        .frame(width: size, height: size)
        .clipShape(Circle())
        .overlay(Circle().stroke(ColorsToken.Border.subtle, lineWidth: StrokeWidthToken.hairline))
    }
}

#if DEBUG
struct Avatar_Previews: PreviewProvider {
    static var previews: some View {
        HStack(spacing: Space.md) {
            Avatar(initials: "VA")
            Avatar(initials: "MA", size: 56)
        }
        .padding(InsetsToken.screen)
    }
}
#endif


