import SwiftUI

public struct CardActionBar: View {
    private let actions: [CardAction]
    private let onAction: (CardAction) -> Void
    public init(actions: [CardAction], onAction: @escaping (CardAction) -> Void) {
        self.actions = actions
        self.onAction = onAction
    }

    public var body: some View {
        HStack(spacing: Space.sm) {
            ForEach(mappedActions) { action in
                MyonButton(action.label, style: actionStyle(for: action)) { onAction(action) }
                    .frame(minWidth: 0)
            }
            Spacer(minLength: 0)
        }
    }

    // Enforce at most one primary CTA; others fall back to secondary/ghost
    private var mappedActions: [CardAction] {
        var sawPrimary = false
        return actions.map { a in
            if a.style == .primary {
                if sawPrimary { return CardAction(kind: a.kind, label: a.label, style: .secondary, iconSystemName: a.iconSystemName, payload: a.payload) }
                sawPrimary = true
                return a
            }
            return a
        }
    }

    private func actionStyle(for action: CardAction) -> MyonButtonStyleKind {
        switch action.style ?? .secondary {
        case .primary: return .primary
        case .secondary: return .secondary
        case .ghost: return .ghost
        case .destructive: return .destructive
        }
    }
}


