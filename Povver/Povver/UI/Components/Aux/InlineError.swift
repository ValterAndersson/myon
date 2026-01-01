import SwiftUI

public struct InlineError: View {
    private let message: String
    public init(_ message: String) { self.message = message }
    public var body: some View {
        HStack(spacing: Space.xs) {
            Image(systemName: "exclamationmark.circle.fill")
                .foregroundColor(ColorsToken.State.error)
                .frame(width: IconSizeToken.md, height: IconSizeToken.md)
            PovverText(message, style: .footnote, color: ColorsToken.State.error)
                .lineLimit(2)
        }
        .padding(.vertical, Space.xs)
        .padding(.horizontal, Space.sm)
        .background(ColorsToken.State.error.opacity(0.08))
        .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.small, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: CornerRadiusToken.small, style: .continuous)
                .stroke(ColorsToken.State.error.opacity(0.25), lineWidth: StrokeWidthToken.hairline)
        )
    }
}


