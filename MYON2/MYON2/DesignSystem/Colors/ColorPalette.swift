import SwiftUI

// MARK: - Design System Colors

extension Color {
    
    // MARK: - Brand Colors
    struct Brand {
        static let primary = Color("BrandPrimary") // Main app color
        static let secondary = Color("BrandSecondary") // Secondary brand color
        static let tertiary = Color("BrandTertiary") // Accent color
    }
    
    // MARK: - Semantic Colors
    struct Semantic {
        // Success states
        static let success = Color("SemanticSuccess")
        static let successLight = Color("SemanticSuccessLight")
        
        // Warning states
        static let warning = Color("SemanticWarning")
        static let warningLight = Color("SemanticWarningLight")
        
        // Error states
        static let error = Color("SemanticError")
        static let errorLight = Color("SemanticErrorLight")
        
        // Info states
        static let info = Color("SemanticInfo")
        static let infoLight = Color("SemanticInfoLight")
    }
    
    // MARK: - Surface Colors
    struct Surface {
        static let primary = Color("SurfacePrimary")
        static let secondary = Color("SurfaceSecondary")
        static let tertiary = Color("SurfaceTertiary")
        static let elevated = Color("SurfaceElevated")
        static let overlay = Color("SurfaceOverlay")
    }
    
    // MARK: - Text Colors
    struct Text {
        static let primary = Color("TextPrimary")
        static let secondary = Color("TextSecondary")
        static let tertiary = Color("TextTertiary")
        static let disabled = Color("TextDisabled")
        static let inverse = Color("TextInverse")
    }
    
    // MARK: - Border Colors
    struct Border {
        static let primary = Color("BorderPrimary")
        static let secondary = Color("BorderSecondary")
        static let focus = Color("BorderFocus")
        static let error = Color("BorderError")
    }
    
    // MARK: - Component Colors
    struct Component {
        static let buttonPrimary = Brand.primary
        static let buttonSecondary = Surface.secondary
        static let buttonDestructive = Semantic.error
        
        static let cardBackground = Surface.primary
        static let cardBorder = Border.secondary
        
        static let inputBackground = Surface.secondary
        static let inputBorder = Border.primary
        static let inputFocus = Border.focus
    }
    
    // MARK: - Utility Colors (for gradual migration from hardcoded colors)
    struct Utility {
        static let blue = Color("UtilityBlue")
        static let red = Color("UtilityRed")
        static let green = Color("UtilityGreen")
        static let orange = Color("UtilityOrange")
        static let purple = Color("UtilityPurple")
        static let gray = Color("UtilityGray")
    }
}

// MARK: - Color Extensions for easier usage

extension Color {
    /// Primary brand color - use for main actions and branding
    static let brandPrimary = Brand.primary
    
    /// Secondary brand color - use for secondary actions
    static let brandSecondary = Brand.secondary
    
    /// Success color - use for positive feedback
    static let success = Semantic.success
    
    /// Warning color - use for cautionary feedback
    static let warning = Semantic.warning
    
    /// Error color - use for negative feedback
    static let error = Semantic.error
    
    /// Info color - use for informational feedback
    static let info = Semantic.info
}

// MARK: - Gradient Helpers

extension Color {
    struct Gradients {
        static let brandPrimary = LinearGradient(
            colors: [Brand.primary, Brand.primary.opacity(0.8)],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
        
        static let success = LinearGradient(
            colors: [Semantic.success, Semantic.successLight],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
        
        static let warning = LinearGradient(
            colors: [Semantic.warning, Semantic.warningLight],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
        
        static let error = LinearGradient(
            colors: [Semantic.error, Semantic.errorLight],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
    }
}