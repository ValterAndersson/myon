import SwiftUI

public struct ListRow<Leading: View, Trailing: View>: View {
    private let title: String
    private let subtitle: String?
    private let leading: Leading
    private let trailing: Trailing
    public init(title: String, subtitle: String? = nil, @ViewBuilder leading: () -> Leading = { EmptyView() }, @ViewBuilder trailing: () -> Trailing = { EmptyView() }) {
        self.title = title
        self.subtitle = subtitle
        self.leading = leading()
        self.trailing = trailing()
    }
    public var body: some View {
        HStack(spacing: Space.md) {
            leading
            VStack(alignment: .leading, spacing: Space.xs) {
                MyonText(title, style: .body)
                if let subtitle { MyonText(subtitle, style: .footnote, color: ColorsToken.Text.secondary) }
            }
            Spacer()
            trailing
        }
        .padding(.vertical, Space.sm)
    }
}


