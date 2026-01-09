import SwiftUI

public struct CardOverflowMenu: View {
    private let actions: [CardAction]
    private let onAction: (CardAction) -> Void
    @State private var show = false
    public init(actions: [CardAction], onAction: @escaping (CardAction) -> Void) {
        self.actions = actions
        self.onAction = onAction
    }

    public var body: some View {
        Menu {
            ForEach(actions) { action in
                Button(action.label) { onAction(action) }
            }
        } label: {
            Icon("ellipsis", size: .md, color: Color.textSecondary)
        }
        .menuStyle(.automatic)
    }
}


