import SwiftUI

public enum BannerKind { case info, success, warning, error }

public struct Banner: View {
    private let title: String
    private let message: String?
    private let kind: BannerKind
    public init(title: String, message: String? = nil, kind: BannerKind = .info) {
        self.title = title
        self.message = message
        self.kind = kind
    }
    public var body: some View {
        HStack(alignment: .top, spacing: Space.sm) {
            Icon(iconName, size: .md, color: onColor)
            VStack(alignment: .leading, spacing: Space.xs) {
                MyonText(title, style: .headline, color: onColor)
                if let message { MyonText(message, style: .subheadline, color: onColor) }
            }
            Spacer()
        }
        .padding(InsetsToken.symmetric(vertical: Space.md, horizontal: Space.lg))
        .background(background)
        .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.large, style: .continuous))
        .shadowStyle(ShadowsToken.level1)
    }

    private var background: Color {
        switch kind {
        case .info: return ColorsToken.State.info.opacity(0.12)
        case .success: return ColorsToken.State.success.opacity(0.12)
        case .warning: return ColorsToken.State.warning.opacity(0.12)
        case .error: return ColorsToken.State.error.opacity(0.12)
        }
    }
    private var onColor: Color {
        switch kind {
        case .info: return ColorsToken.State.info
        case .success: return ColorsToken.State.success
        case .warning: return ColorsToken.State.warning
        case .error: return ColorsToken.State.error
        }
    }
    private var iconName: String {
        switch kind {
        case .info: return "info.circle.fill"
        case .success: return "checkmark.seal.fill"
        case .warning: return "exclamationmark.triangle.fill"
        case .error: return "xmark.octagon.fill"
        }
    }
}


