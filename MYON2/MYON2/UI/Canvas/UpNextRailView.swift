import SwiftUI

public struct UpNextRailView: View {
    private let cards: [CanvasCardModel]
    private let upNextIds: [String]
    private let onTap: (String) -> Void
    private let displayCap: Int = 20
    public init(cards: [CanvasCardModel], upNextIds: [String], onTap: @escaping (String) -> Void) {
        self.cards = cards
        self.upNextIds = upNextIds
        self.onTap = onTap
    }
    public var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: Space.sm) {
                let prefixIds = Array(upNextIds.prefix(displayCap))
                ForEach(prefixIds, id: \.self) { id in
                    if let card = cards.first(where: { $0.id == id }) {
                        Button(action: { onTap(id) }) {
                            HStack(spacing: Space.xs) {
                                StatusTag(card.type.rawValue, kind: .info)
                                if let t = card.title { MyonText(t, style: .footnote, color: ColorsToken.Text.primary) }
                            }
                            .padding(.vertical, Space.xs)
                            .padding(.horizontal, Space.sm)
                            .background(ColorsToken.Surface.default)
                            .clipShape(Capsule())
                            .overlay(Capsule().stroke(ColorsToken.Border.subtle, lineWidth: StrokeWidthToken.hairline))
                        }
                    }
                }
                if upNextIds.count > displayCap {
                    let overflow = upNextIds.count - displayCap
                    HStack(spacing: Space.xs) {
                        MyonText("+\(overflow)", style: .footnote, color: ColorsToken.Text.secondary)
                    }
                    .padding(.vertical, Space.xs)
                    .padding(.horizontal, Space.sm)
                    .background(ColorsToken.Surface.default)
                    .clipShape(Capsule())
                    .overlay(Capsule().stroke(ColorsToken.Border.subtle, lineWidth: StrokeWidthToken.hairline))
                }
            }
            .padding(.horizontal, Space.lg)
        }
        .frame(height: 44)
        .background(VisualEffectBlur(style: .systemUltraThinMaterial))
        .overlay(Divider().background(ColorsToken.Border.subtle), alignment: .bottom)
        .ignoresSafeArea(edges: .horizontal)
    }
}


