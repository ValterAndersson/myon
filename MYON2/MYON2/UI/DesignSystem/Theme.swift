import SwiftUI

/// MYON theme container to allow future theming overrides via Environment.
public struct MyonTheme: Equatable {
    public var cornerRadiusSmall: CGFloat = CornerRadiusToken.small
    public var cornerRadiusMedium: CGFloat = CornerRadiusToken.medium
    public var cornerRadiusLarge: CGFloat = CornerRadiusToken.large
    public var buttonHeight: CGFloat = 48
    public var hitTargetMin: CGFloat = 44
    public var stackSpacing: CGFloat = LayoutToken.stackSpacing
    public init() {}
}

private struct MyonThemeKey: EnvironmentKey {
    static let defaultValue: MyonTheme = MyonTheme()
}

public extension EnvironmentValues {
    var myonTheme: MyonTheme {
        get { self[MyonThemeKey.self] }
        set { self[MyonThemeKey.self] = newValue }
    }
}

public extension View {
    func myonTheme(_ theme: MyonTheme) -> some View {
        environment(\.myonTheme, theme)
    }
}


