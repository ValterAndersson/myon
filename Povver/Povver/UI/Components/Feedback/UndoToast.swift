import SwiftUI

public struct UndoToast: View {
    private let text: String
    private let onUndo: () -> Void
    public init(_ text: String, onUndo: @escaping () -> Void) {
        self.text = text
        self.onUndo = onUndo
    }
    public var body: some View {
        HStack(spacing: Space.md) {
            PovverText(text, style: .callout, color: Color.textInverse)
            PovverButton("Undo", style: .secondary) { onUndo() }
                .tint(.textInverse)
        }
        .padding(InsetsToken.symmetric(vertical: Space.sm, horizontal: Space.md))
        .background(Color.accent)
        .clipShape(Capsule())
        .shadowStyle(ShadowsToken.level2)
    }
}


