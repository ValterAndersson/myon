import SwiftUI

public enum StatusKind { case info, success, warning, error }

public struct StatusTag: View {
    private let text: String
    private let kind: StatusKind
    public init(_ text: String, kind: StatusKind = .info) {
        self.text = text
        self.kind = kind
    }

    public var body: some View {
        SwiftUI.Text(text)
            .font(TypographyToken.footnote)
            .foregroundColor(foreground())
            .padding(.vertical, Space.xs)
            .padding(.horizontal, Space.sm)
            .background(background())
            .clipShape(Capsule())
            .overlay(
                Capsule().stroke(ColorsToken.Border.subtle, lineWidth: StrokeWidthToken.hairline)
            )
    }

    private func background() -> Color {
        switch kind {
        case .info: return ColorsToken.Brand.accent100
        case .success: return ColorsToken.State.success.opacity(0.12)
        case .warning: return ColorsToken.State.warning.opacity(0.12)
        case .error: return ColorsToken.State.error.opacity(0.12)
        }
    }

    private func foreground() -> Color {
        switch kind {
        case .info: return ColorsToken.Brand.accent900
        case .success: return ColorsToken.State.success
        case .warning: return ColorsToken.State.warning
        case .error: return ColorsToken.State.error
        }
    }
}

#if DEBUG
struct StatusTag_Previews: PreviewProvider {
    static var previews: some View {
        HStack(spacing: Space.sm) {
            StatusTag("Info")
            StatusTag("Success", kind: .success)
            StatusTag("Warn", kind: .warning)
            StatusTag("Error", kind: .error)
        }
        .padding(InsetsToken.screen)
    }
}
#endif


