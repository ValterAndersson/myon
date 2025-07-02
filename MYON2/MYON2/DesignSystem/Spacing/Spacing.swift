import SwiftUI

// MARK: - Design System Spacing

struct Spacing {
    
    // MARK: - Base Spacing Values (8-point grid system)
    static let xs: CGFloat = 4      // Extra small spacing
    static let sm: CGFloat = 8      // Small spacing
    static let md: CGFloat = 16     // Medium spacing (base unit)
    static let lg: CGFloat = 24     // Large spacing
    static let xl: CGFloat = 32     // Extra large spacing
    static let xxl: CGFloat = 48    // Double extra large spacing
    static let xxxl: CGFloat = 64   // Triple extra large spacing
    
    // MARK: - Semantic Spacing Values
    static let none: CGFloat = 0
    static let hairline: CGFloat = 1
    static let tiny: CGFloat = 2
    static let micro: CGFloat = xs
    static let small: CGFloat = sm
    static let medium: CGFloat = md
    static let large: CGFloat = lg
    static let huge: CGFloat = xl
    static let massive: CGFloat = xxl
    
    // MARK: - Component-Specific Spacing
    struct Component {
        // Button spacing
        static let buttonPaddingHorizontal: CGFloat = md
        static let buttonPaddingVertical: CGFloat = sm + xs // 12pt
        static let buttonSpacing: CGFloat = sm
        
        // Card spacing
        static let cardPadding: CGFloat = md
        static let cardSpacing: CGFloat = md
        static let cardCornerRadius: CGFloat = sm + xs // 12pt
        
        // Form spacing
        static let formFieldSpacing: CGFloat = md
        static let formSectionSpacing: CGFloat = lg
        static let formLabelSpacing: CGFloat = xs
        
        // List spacing
        static let listItemPadding: CGFloat = md
        static let listItemSpacing: CGFloat = sm
        static let listSectionSpacing: CGFloat = lg
        
        // Navigation spacing
        static let navigationPadding: CGFloat = md
        static let tabBarHeight: CGFloat = 48
        
        // Modal spacing
        static let modalPadding: CGFloat = lg
        static let modalCornerRadius: CGFloat = md
        
        // Icon spacing
        static let iconSpacing: CGFloat = sm
        static let iconPadding: CGFloat = xs
    }
    
    // MARK: - Layout Spacing
    struct Layout {
        // Screen margins
        static let screenMargin: CGFloat = md
        static let screenMarginLarge: CGFloat = lg
        
        // Section spacing
        static let sectionSpacing: CGFloat = lg
        static let sectionPadding: CGFloat = md
        
        // Content spacing
        static let contentSpacing: CGFloat = md
        static let contentPadding: CGFloat = md
        
        // Grid spacing
        static let gridSpacing: CGFloat = md
        static let gridItemSpacing: CGFloat = sm
    }
}

// MARK: - Padding Extensions

extension View {
    
    // MARK: - Basic Padding
    func paddingXS() -> some View {
        self.padding(Spacing.xs)
    }
    
    func paddingSM() -> some View {
        self.padding(Spacing.sm)
    }
    
    func paddingMD() -> some View {
        self.padding(Spacing.md)
    }
    
    func paddingLG() -> some View {
        self.padding(Spacing.lg)
    }
    
    func paddingXL() -> some View {
        self.padding(Spacing.xl)
    }
    
    func paddingXXL() -> some View {
        self.padding(Spacing.xxl)
    }
    
    // MARK: - Directional Padding
    func paddingHorizontal(_ amount: CGFloat = Spacing.md) -> some View {
        self.padding(.horizontal, amount)
    }
    
    func paddingVertical(_ amount: CGFloat = Spacing.md) -> some View {
        self.padding(.vertical, amount)
    }
    
    func paddingTop(_ amount: CGFloat = Spacing.md) -> some View {
        self.padding(.top, amount)
    }
    
    func paddingBottom(_ amount: CGFloat = Spacing.md) -> some View {
        self.padding(.bottom, amount)
    }
    
    func paddingLeading(_ amount: CGFloat = Spacing.md) -> some View {
        self.padding(.leading, amount)
    }
    
    func paddingTrailing(_ amount: CGFloat = Spacing.md) -> some View {
        self.padding(.trailing, amount)
    }
    
    // MARK: - Semantic Padding
    func screenMargins() -> some View {
        self.paddingHorizontal(Spacing.Layout.screenMargin)
    }
    
    func cardPadding() -> some View {
        self.padding(Spacing.Component.cardPadding)
    }
    
    func buttonPadding() -> some View {
        self.padding(.horizontal, Spacing.Component.buttonPaddingHorizontal)
            .padding(.vertical, Spacing.Component.buttonPaddingVertical)
    }
    
    func formFieldPadding() -> some View {
        self.paddingVertical(Spacing.Component.formFieldSpacing)
    }
    
    func listItemPadding() -> some View {
        self.padding(Spacing.Component.listItemPadding)
    }
    
    func modalPadding() -> some View {
        self.padding(Spacing.Component.modalPadding)
    }
}

// MARK: - Spacing Extensions

extension View {
    
    // MARK: - Spacer Helpers
    static func spacerXS() -> some View {
        Spacer()
            .frame(height: Spacing.xs)
    }
    
    static func spacerSM() -> some View {
        Spacer()
            .frame(height: Spacing.sm)
    }
    
    static func spacerMD() -> some View {
        Spacer()
            .frame(height: Spacing.md)
    }
    
    static func spacerLG() -> some View {
        Spacer()
            .frame(height: Spacing.lg)
    }
    
    static func spacerXL() -> some View {
        Spacer()
            .frame(height: Spacing.xl)
    }
    
    // MARK: - Spacing Between Elements
    func spacingXS() -> some View {
        VStack(spacing: Spacing.xs) {
            self
        }
    }
    
    func spacingSM() -> some View {
        VStack(spacing: Spacing.sm) {
            self
        }
    }
    
    func spacingMD() -> some View {
        VStack(spacing: Spacing.md) {
            self
        }
    }
    
    func spacingLG() -> some View {
        VStack(spacing: Spacing.lg) {
            self
        }
    }
    
    func spacingXL() -> some View {
        VStack(spacing: Spacing.xl) {
            self
        }
    }
}

// MARK: - Corner Radius Extensions

extension View {
    
    func cornerRadiusXS() -> some View {
        self.cornerRadius(Spacing.xs)
    }
    
    func cornerRadiusSM() -> some View {
        self.cornerRadius(Spacing.sm)
    }
    
    func cornerRadiusMD() -> some View {
        self.cornerRadius(Spacing.md)
    }
    
    func cornerRadiusLG() -> some View {
        self.cornerRadius(Spacing.lg)
    }
    
    func cardCornerRadius() -> some View {
        self.cornerRadius(Spacing.Component.cardCornerRadius)
    }
    
    func modalCornerRadius() -> some View {
        self.cornerRadius(Spacing.Component.modalCornerRadius)
    }
}

// MARK: - Layout Helpers

extension View {
    
    // MARK: - Frame Helpers with Spacing
    func frameSquare(_ size: CGFloat) -> some View {
        self.frame(width: size, height: size)
    }
    
    func frameIcon() -> some View {
        self.frameSquare(Spacing.lg)
    }
    
    func frameIconLarge() -> some View {
        self.frameSquare(Spacing.xl)
    }
    
    func frameButton() -> some View {
        self.frame(minHeight: 44) // iOS minimum touch target
    }
    
    // MARK: - Common Layout Patterns
    func cardContainer() -> some View {
        self
            .cardPadding()
            .background(Color.Surface.primary)
            .cardCornerRadius()
            .shadow(radius: 2)
    }
    
    func sectionContainer() -> some View {
        self
            .padding(Spacing.Layout.sectionPadding)
            .background(Color.Surface.primary)
    }
    
    func screenContainer() -> some View {
        self
            .screenMargins()
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Color.Surface.primary)
    }
}