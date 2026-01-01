import SwiftUI
import UIKit

/// Centralized design tokens for spacing, typography, colors, motion, and elevation.
/// These tokens aim to be stable and composable; components should consume tokens rather than hard-coded values.

// MARK: - Light/Dark Mode Color Helper

public extension Color {
    /// Initialize a color that adapts to light/dark mode
    init(light: Color, dark: Color) {
        self.init(UIColor { traitCollection in
            traitCollection.userInterfaceStyle == .dark 
                ? UIColor(dark) 
                : UIColor(light)
        })
    }
    
    /// Initialize from hex string
    init(hex: String) {
        let hex = hex.trimmingCharacters(in: CharacterSet.alphanumerics.inverted)
        var int: UInt64 = 0
        Scanner(string: hex).scanHexInt64(&int)
        let a, r, g, b: UInt64
        switch hex.count {
        case 3: // RGB (12-bit)
            (a, r, g, b) = (255, (int >> 8) * 17, (int >> 4 & 0xF) * 17, (int & 0xF) * 17)
        case 6: // RGB (24-bit)
            (a, r, g, b) = (255, int >> 16, int >> 8 & 0xFF, int & 0xFF)
        case 8: // ARGB (32-bit)
            (a, r, g, b) = (int >> 24, int >> 16 & 0xFF, int >> 8 & 0xFF, int & 0xFF)
        default:
            (a, r, g, b) = (1, 1, 1, 0)
        }
        self.init(
            .sRGB,
            red: Double(r) / 255,
            green: Double(g) / 255,
            blue: Double(b) / 255,
            opacity: Double(a) / 255
        )
    }
}
public enum Space {
    public static let zero: CGFloat = 0
    public static let xxs: CGFloat = 2
    public static let xs: CGFloat = 4
    public static let sm: CGFloat = 8
    public static let md: CGFloat = 12
    public static let lg: CGFloat = 16
    public static let xl: CGFloat = 24
    public static let xxl: CGFloat = 32
    public static let xxxl: CGFloat = 40
}

public enum CornerRadiusToken {
    public static let small: CGFloat = 8
    public static let medium: CGFloat = 12
    public static let large: CGFloat = 16
    public static let card: CGFloat = 18
    public static let pill: CGFloat = 999
}

public enum StrokeWidthToken {
    /// Hairline stroke adjusted for device scale
    public static var hairline: CGFloat { max(1.0 / UIScreen.main.scale, 0.5) }
    public static let thin: CGFloat = 1
    public static let thick: CGFloat = 2
}

public enum IconSizeToken {
    public static let sm: CGFloat = 16
    public static let md: CGFloat = 20
    public static let lg: CGFloat = 24
    public static let xl: CGFloat = 28
    public static let xxl: CGFloat = 32
}

public enum MotionToken {
    /// Recommended durations (seconds)
    public static let fast: Double = 0.12
    public static let medium: Double = 0.20
    public static let slow: Double = 0.35
}

public struct ShadowStyle: Equatable {
    public let color: Color
    public let x: CGFloat
    public let y: CGFloat
    public let blur: CGFloat
    public let spread: CGFloat
    public init(color: Color, x: CGFloat, y: CGFloat, blur: CGFloat, spread: CGFloat = 0) {
        self.color = color
        self.x = x
        self.y = y
        self.blur = blur
        self.spread = spread
    }
}

public enum ShadowsToken {
    /// Subtle base shadow used for most cards (tool-like UI)
    public static let level1 = ShadowStyle(color: .black.opacity(0.06), x: 0, y: 1, blur: 8)
    /// Hover/raised
    public static let level2 = ShadowStyle(color: .black.opacity(0.08), x: 0, y: 2, blur: 16)
    /// Prominent
    public static let level3 = ShadowStyle(color: .black.opacity(0.16), x: 0, y: 12, blur: 32)
}

public enum TypographyToken {
    public static var display: Font { .system(size: 34, weight: .bold, design: .default) }
    public static var title1: Font { .system(size: 28, weight: .semibold, design: .default) }
    public static var title2: Font { .system(size: 22, weight: .semibold, design: .default) }
    public static var title3: Font { .system(size: 20, weight: .semibold, design: .default) }
    public static var headline: Font { .system(size: 17, weight: .semibold, design: .default) }
    public static var body: Font { .system(size: 17, weight: .regular, design: .default) }
    public static var callout: Font { .system(size: 16, weight: .regular, design: .default) }
    public static var subheadline: Font { .system(size: 15, weight: .regular, design: .default) }
    public static var footnote: Font { .system(size: 13, weight: .regular, design: .default) }
    public static var caption: Font { .system(size: 12, weight: .regular, design: .default) }
    public static var button: Font { .system(size: 17, weight: .semibold, design: .default) }
    public static var monospaceSmall: Font { .system(size: 13, weight: .regular, design: .monospaced) }
}

public enum ColorsToken {
    /// Neutral scale for borders, text, and tints
    public enum Neutral {
        public static var n50: Color { Color(red: 0.97, green: 0.98, blue: 0.99) }
        public static var n100: Color { Color(red: 0.94, green: 0.96, blue: 0.97) }
        public static var n200: Color { Color(red: 0.91, green: 0.94, blue: 0.96) }
        public static var n300: Color { Color(red: 0.85, green: 0.89, blue: 0.93) }
        public static var n400: Color { Color(red: 0.80, green: 0.85, blue: 0.89) }
        public static var n500: Color { Color(red: 0.60, green: 0.67, blue: 0.74) }
        public static var n600: Color { Color(red: 0.45, green: 0.53, blue: 0.61) }
        public static var n700: Color { Color(red: 0.34, green: 0.41, blue: 0.49) }
        public static var n800: Color { Color(red: 0.22, green: 0.28, blue: 0.35) }
        public static var n900: Color { Color(red: 0.12, green: 0.16, blue: 0.20) }
    }
    public enum Brand {
        /// Functional accent palette (teal/mint)
        public static var accent100: Color { Color(red: 0.75, green: 0.94, blue: 0.89) } // tint for chips/fills
        public static var accent700: Color { Color(red: 0.16, green: 0.73, blue: 0.56) } // default accent
        public static var accent900: Color { Color(red: 0.09, green: 0.48, blue: 0.39) } // text-on-white contrast
        public static var primary: Color { accent700 }
        public static var secondary: Color { accent900 }
        
        /// Emerald button fills and strokes for primary actions
        public static var emeraldFill: Color { accent700 }
        public static var emeraldStroke: Color { accent900 }
    }
    public enum Background {
        public static var primary: Color { Color.white.opacity(0.98) }
        public static var secondary: Color { ColorsToken.Neutral.n50 }
        /// Off-white screen background for premium surfaces
        public static var screen: Color { Color(hex: "FAFBFC") }
    }
    public enum Surface {
        public static var `default`: Color { Color.white } 
        public static var raised: Color { Color.white }
        /// Plain card surface
        public static var card: Color { Color.white }
        /// Active card surface (same color, but used with elevated shadow/stroke)
        public static var cardActive: Color { Color.white }
        
        // MARK: - Semantic Selection Surfaces (Light/Dark Ready)
        
        /// Selected/focused row background - NOT brand-derived for dark mode compatibility
        public static var focusedRow: Color { 
            Color(
                light: Color(hex: "E8F0FE"),   // Soft blue tint in light mode
                dark: Color(hex: "1A3352")     // Deep blue for dark mode
            )
        }
        
        /// Row being actively edited
        public static var editingRow: Color { 
            Color(
                light: Color(hex: "F1F5F9"),   // Neutral slate
                dark: Color(hex: "1E293B")     // Slate dark
            )
        }
        
        /// Grid header row background
        public static var headerBar: Color {
            Color(
                light: ColorsToken.Neutral.n100,
                dark: Color(hex: "1E1E1E")
            )
        }
        
        /// Alternating row for tables/grids
        public static var alternateRow: Color {
            Color(
                light: ColorsToken.Neutral.n50.opacity(0.5),
                dark: Color(hex: "252525").opacity(0.5)
            )
        }
    }
    public enum Border {
        public static var `default`: Color { ColorsToken.Neutral.n300 }
        public static var subtle: Color { ColorsToken.Neutral.n200 }
    }
    
    /// Stroke colors for cards and containers
    public enum Stroke {
        /// Card hairline stroke (~8% black opacity)
        public static var card: Color { Color.black.opacity(0.08) }
        /// Active card stroke (brand accent)
        public static var cardActive: Color { ColorsToken.Brand.primary }
    }
    
    /// Separator/divider colors with dark mode support
    public enum Separator {
        public static var hairline: Color {
            Color(
                light: ColorsToken.Neutral.n200,
                dark: Color(hex: "333333")
            )
        }
        public static var `default`: Color {
            Color(
                light: ColorsToken.Neutral.n300,
                dark: Color(hex: "404040")
            )
        }
        /// Dotted divider for warmup/working set separation
        public static var dottedWarmup: Color {
            Color(
                light: ColorsToken.Neutral.n400,
                dark: Color(hex: "555555")
            )
        }
    }
    public enum Text {
        public static var primary: Color { ColorsToken.Neutral.n900 }
        public static var secondary: Color { ColorsToken.Neutral.n700 }
        public static var inverse: Color { Color.white }
        public static var muted: Color { ColorsToken.Neutral.n600 }
    }
    public enum State {
        public static var success: Color { Color(uiColor: .systemGreen) }
        public static var warning: Color { Color(uiColor: .systemYellow) }
        public static var error: Color { Color(uiColor: .systemRed) }
        public static var info: Color { Color(uiColor: .systemBlue) }
    }
}

public enum InsetsToken {
    public static func all(_ v: CGFloat) -> EdgeInsets { EdgeInsets(top: v, leading: v, bottom: v, trailing: v) }
    public static func symmetric(vertical: CGFloat, horizontal: CGFloat) -> EdgeInsets {
        EdgeInsets(top: vertical, leading: horizontal, bottom: vertical, trailing: horizontal)
    }
    public static let screen = EdgeInsets(top: Space.lg, leading: Space.lg, bottom: Space.lg, trailing: Space.lg)
}

public enum LayoutToken {
    /// Grid unit (points)
    public static let gridUnit: CGFloat = 8
    /// Default inter-item spacing for stacks
    public static let stackSpacing: CGFloat = Space.md
    /// Default canvas column count for grid layouts
    public static let canvasColumns: Int = 12
    /// Max content width for centered pages (points)
    public static let contentMaxWidth: CGFloat = 860
    /// Extra padding for bottom CTAs (added to safe area inset at runtime)
    public static let bottomCTAExtraPadding: CGFloat = 24
}

public extension View {
    /// Apply a consistent shadow using a design token
    func shadowStyle(_ style: ShadowStyle) -> some View {
        shadow(color: style.color, radius: style.blur, x: style.x, y: style.y)
    }
}
