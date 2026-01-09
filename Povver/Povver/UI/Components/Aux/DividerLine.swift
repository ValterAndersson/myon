import SwiftUI

public struct DividerLine: View {
    private let inset: CGFloat
    public init(inset: CGFloat = 0) { self.inset = inset }
    public var body: some View {
        Rectangle()
            .fill(Color.separator)
            .frame(height: StrokeWidthToken.hairline)
            .padding(.leading, inset)
    }
}


