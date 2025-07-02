import SwiftUI

// MARK: - Design System Typography

extension Font {
    
    // MARK: - Display Fonts (Large, attention-grabbing text)
    struct Display {
        static let large = Font.system(size: 57, weight: .regular, design: .default)
        static let medium = Font.system(size: 45, weight: .regular, design: .default)
        static let small = Font.system(size: 36, weight: .regular, design: .default)
    }
    
    // MARK: - Headline Fonts (Page and section headers)
    struct Headline {
        static let large = Font.system(size: 32, weight: .regular, design: .default)
        static let medium = Font.system(size: 28, weight: .regular, design: .default)
        static let small = Font.system(size: 24, weight: .regular, design: .default)
    }
    
    // MARK: - Title Fonts (Content hierarchy)
    struct Title {
        static let large = Font.system(size: 22, weight: .regular, design: .default)
        static let medium = Font.system(size: 20, weight: .medium, design: .default)
        static let small = Font.system(size: 18, weight: .medium, design: .default)
    }
    
    // MARK: - Body Fonts (Main content)
    struct Body {
        static let large = Font.system(size: 17, weight: .regular, design: .default)
        static let medium = Font.system(size: 16, weight: .regular, design: .default)
        static let small = Font.system(size: 15, weight: .regular, design: .default)
    }
    
    // MARK: - Label Fonts (UI elements, buttons, form labels)
    struct Label {
        static let large = Font.system(size: 17, weight: .semibold, design: .default)
        static let medium = Font.system(size: 16, weight: .semibold, design: .default)
        static let small = Font.system(size: 15, weight: .semibold, design: .default)
    }
    
    // MARK: - Caption Fonts (Supporting text, metadata)
    struct Caption {
        static let large = Font.system(size: 14, weight: .regular, design: .default)
        static let medium = Font.system(size: 13, weight: .regular, design: .default)
        static let small = Font.system(size: 12, weight: .regular, design: .default)
    }
    
    // MARK: - Specialized Fonts
    struct Specialized {
        // Monospace for code, numbers, data
        static let code = Font.system(size: 16, weight: .regular, design: .monospaced)
        static let codeSmall = Font.system(size: 14, weight: .regular, design: .monospaced)
        
        // Rounded for playful, modern feel
        static let rounded = Font.system(size: 16, weight: .medium, design: .rounded)
        static let roundedLarge = Font.system(size: 20, weight: .medium, design: .rounded)
    }
}

// MARK: - Text Styles with Semantic Meaning

extension Text {
    
    // MARK: - Semantic Text Styles
    func displayLarge() -> some View {
        self.font(.Display.large)
            .lineSpacing(4)
    }
    
    func displayMedium() -> some View {
        self.font(.Display.medium)
            .lineSpacing(3)
    }
    
    func displaySmall() -> some View {
        self.font(.Display.small)
            .lineSpacing(2)
    }
    
    func headlineLarge() -> some View {
        self.font(.Headline.large)
            .lineSpacing(2)
    }
    
    func headlineMedium() -> some View {
        self.font(.Headline.medium)
            .lineSpacing(2)
    }
    
    func headlineSmall() -> some View {
        self.font(.Headline.small)
            .lineSpacing(1)
    }
    
    func titleLarge() -> some View {
        self.font(.Title.large)
            .lineSpacing(1)
    }
    
    func titleMedium() -> some View {
        self.font(.Title.medium)
            .lineSpacing(1)
    }
    
    func titleSmall() -> some View {
        self.font(.Title.small)
            .lineSpacing(1)
    }
    
    func bodyLarge() -> some View {
        self.font(.Body.large)
            .lineSpacing(2)
    }
    
    func bodyMedium() -> some View {
        self.font(.Body.medium)
            .lineSpacing(2)
    }
    
    func bodySmall() -> some View {
        self.font(.Body.small)
            .lineSpacing(1)
    }
    
    func labelLarge() -> some View {
        self.font(.Label.large)
    }
    
    func labelMedium() -> some View {
        self.font(.Label.medium)
    }
    
    func labelSmall() -> some View {
        self.font(.Label.small)
    }
    
    func captionLarge() -> some View {
        self.font(.Caption.large)
            .lineSpacing(1)
    }
    
    func captionMedium() -> some View {
        self.font(.Caption.medium)
            .lineSpacing(1)
    }
    
    func captionSmall() -> some View {
        self.font(.Caption.small)
    }
    
    // MARK: - Specialized Text Styles
    func code() -> some View {
        self.font(.Specialized.code)
            .padding(.horizontal, 4)
            .padding(.vertical, 2)
            .background(Color.Surface.secondary)
            .cornerRadius(4)
    }
    
    func codeSmall() -> some View {
        self.font(.Specialized.codeSmall)
            .padding(.horizontal, 3)
            .padding(.vertical, 1)
            .background(Color.Surface.secondary)
            .cornerRadius(3)
    }
    
    func rounded() -> some View {
        self.font(.Specialized.rounded)
    }
    
    func roundedLarge() -> some View {
        self.font(.Specialized.roundedLarge)
    }
    
    // MARK: - Text Color Styles
    func primaryText() -> some View {
        self.foregroundColor(.Text.primary)
    }
    
    func secondaryText() -> some View {
        self.foregroundColor(.Text.secondary)
    }
    
    func tertiaryText() -> some View {
        self.foregroundColor(.Text.tertiary)
    }
    
    func disabledText() -> some View {
        self.foregroundColor(.Text.disabled)
    }
    
    func inverseText() -> some View {
        self.foregroundColor(.Text.inverse)
    }
    
    func brandText() -> some View {
        self.foregroundColor(.Brand.primary)
    }
    
    func successText() -> some View {
        self.foregroundColor(.Semantic.success)
    }
    
    func warningText() -> some View {
        self.foregroundColor(.Semantic.warning)
    }
    
    func errorText() -> some View {
        self.foregroundColor(.Semantic.error)
    }
    
    func infoText() -> some View {
        self.foregroundColor(.Semantic.info)
    }
}

// MARK: - Text Style Presets for Common Use Cases

extension Text {
    
    // Page titles
    static func pageTitle(_ text: String) -> some View {
        Text(text)
            .headlineLarge()
            .primaryText()
            .multilineTextAlignment(.leading)
    }
    
    // Section headers
    static func sectionHeader(_ text: String) -> some View {
        Text(text)
            .titleMedium()
            .primaryText()
            .multilineTextAlignment(.leading)
    }
    
    // Card titles
    static func cardTitle(_ text: String) -> some View {
        Text(text)
            .titleSmall()
            .primaryText()
            .multilineTextAlignment(.leading)
    }
    
    // Primary content
    static func content(_ text: String) -> some View {
        Text(text)
            .bodyMedium()
            .primaryText()
            .multilineTextAlignment(.leading)
    }
    
    // Supporting content
    static func supportingContent(_ text: String) -> some View {
        Text(text)
            .bodySmall()
            .secondaryText()
            .multilineTextAlignment(.leading)
    }
    
    // Button labels
    static func buttonLabel(_ text: String) -> some View {
        Text(text)
            .labelMedium()
    }
    
    // Form labels
    static func formLabel(_ text: String) -> some View {
        Text(text)
            .labelSmall()
            .secondaryText()
    }
    
    // Metadata and timestamps
    static func metadata(_ text: String) -> some View {
        Text(text)
            .captionMedium()
            .tertiaryText()
    }
}