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
            MyonText(text, style: .callout, color: ColorsToken.Text.inverse)
            MyonButton("Undo", style: .secondary) { onUndo() }
                .tint(.white)
        }
        .padding(InsetsToken.symmetric(vertical: Space.sm, horizontal: Space.md))
        .background(ColorsToken.Brand.primary)
        .clipShape(Capsule())
        .shadowStyle(ShadowsToken.level2)
    }
}


