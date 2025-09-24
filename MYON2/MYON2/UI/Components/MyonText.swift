import SwiftUI

public enum MyonTextStyle {
    case display, title1, title2, title3
    case headline, body, callout, subheadline, footnote, caption
}

public struct MyonText: View {
    private let text: String
    private let style: MyonTextStyle
    private let color: Color
    private let align: TextAlignment
    private let lineLimit: Int?

    public init(_ text: String, style: MyonTextStyle = .body, color: Color = ColorsToken.Text.primary, align: TextAlignment = .leading, lineLimit: Int? = nil) {
        self.text = text
        self.style = style
        self.color = color
        self.align = align
        self.lineLimit = lineLimit
    }

    public var body: some View {
        SwiftUI.Text(text)
            .font(font(for: style))
            .foregroundColor(color)
            .multilineTextAlignment(align)
            .lineLimit(lineLimit)
    }

    private func font(for style: MyonTextStyle) -> Font {
        switch style {
        case .display: return TypographyToken.display
        case .title1: return TypographyToken.title1
        case .title2: return TypographyToken.title2
        case .title3: return TypographyToken.title3
        case .headline: return TypographyToken.headline
        case .body: return TypographyToken.body
        case .callout: return TypographyToken.callout
        case .subheadline: return TypographyToken.subheadline
        case .footnote: return TypographyToken.footnote
        case .caption: return TypographyToken.caption
        }
    }
}

#if DEBUG
struct MyonText_Previews: PreviewProvider {
    static var previews: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Space.md) {
                MyonText("Display", style: .display)
                MyonText("Title 1", style: .title1)
                MyonText("Title 2", style: .title2)
                MyonText("Title 3", style: .title3)
                MyonText("Headline", style: .headline)
                MyonText("Body", style: .body)
                MyonText("Callout", style: .callout)
                MyonText("Subheadline", style: .subheadline)
                MyonText("Footnote", style: .footnote)
                MyonText("Caption", style: .caption)
            }
            .padding(InsetsToken.screen)
        }
    }
}
#endif


