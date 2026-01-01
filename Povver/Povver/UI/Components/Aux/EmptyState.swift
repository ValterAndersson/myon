import SwiftUI

public struct EmptyState: View {
    private let title: String
    private let message: String?
    private let actionTitle: String?
    private let action: (() -> Void)?

    public init(title: String, message: String? = nil, actionTitle: String? = nil, action: (() -> Void)? = nil) {
        self.title = title
        self.message = message
        self.actionTitle = actionTitle
        self.action = action
    }

    public var body: some View {
        VStack(spacing: Space.md) {
            Image(systemName: "waveform")
                .resizable()
                .scaledToFit()
                .frame(width: 56, height: 56)
                .foregroundColor(ColorsToken.State.info)
            PovverText(title, style: .title2)
            if let message { PovverText(message, style: .callout, color: ColorsToken.Text.secondary, align: .center) }
            if let actionTitle, let action {
                PovverButton(actionTitle, style: .primary, action: action)
                    .frame(maxWidth: 280)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(InsetsToken.screen)
    }
}

#if DEBUG
struct EmptyState_Previews: PreviewProvider {
    static var previews: some View {
        EmptyState(title: "No workouts yet", message: "Start a session to see your workout rail here.", actionTitle: "Start session", action: {})
    }
}
#endif


