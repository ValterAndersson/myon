import SwiftUI

public struct CardContainer<Content: View>: View {
    private let status: CardStatus
    private let content: Content
    public init(status: CardStatus = .active, @ViewBuilder content: () -> Content) {
        self.status = status
        self.content = content()
    }
    public var body: some View {
        SurfaceCard(elevation: elevationForStatus(), backgroundColor: ColorsToken.Surface.card) {
            content
        }
        .opacity(status == .expired ? 0.5 : 1)
    }
    private func elevationForStatus() -> ShadowStyle {
        switch status {
        case .proposed: return ShadowsToken.level1
        case .active: return ShadowsToken.level1
        case .accepted: return ShadowsToken.level2
        case .rejected: return ShadowsToken.level1
        case .expired: return ShadowsToken.level1
        case .completed: return ShadowsToken.level1
        }
    }
}


