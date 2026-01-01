import SwiftUI

public struct VisualEffectBlur: UIViewRepresentable {
    public typealias UIViewType = UIVisualEffectView
    private let style: UIBlurEffect.Style
    public init(style: UIBlurEffect.Style) { self.style = style }
    public func makeUIView(context: Context) -> UIVisualEffectView {
        UIVisualEffectView(effect: UIBlurEffect(style: style))
    }
    public func updateUIView(_ uiView: UIVisualEffectView, context: Context) {
        uiView.effect = UIBlurEffect(style: style)
    }
}
