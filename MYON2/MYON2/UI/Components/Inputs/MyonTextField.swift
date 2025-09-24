import SwiftUI

public struct MyonTextField: View {
    private let title: String
    @Binding private var text: String
    private let placeholder: String
    private let validation: ValidationState
    private let keyboard: UIKeyboardType
    private let autocapitalization: TextInputAutocapitalization
    private let isSecure: Bool
    @FocusState private var focused: Bool

    public init(_ title: String, text: Binding<String>, placeholder: String = "", validation: ValidationState = .normal, keyboard: UIKeyboardType = .default, autocapitalization: TextInputAutocapitalization = .sentences, isSecure: Bool = false) {
        self.title = title
        self._text = text
        self.placeholder = placeholder
        self.validation = validation
        self.keyboard = keyboard
        self.autocapitalization = autocapitalization
        self.isSecure = isSecure
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: Space.xs) {
            MyonText(title, style: .subheadline, color: ColorsToken.Text.secondary)
            HStack(spacing: Space.sm) {
                if isSecure {
                    SecureField(placeholder, text: $text)
                        .textInputAutocapitalization(autocapitalization)
                        .keyboardType(keyboard)
                        .focused($focused)
                } else {
                    TextField(placeholder, text: $text)
                        .textInputAutocapitalization(autocapitalization)
                        .keyboardType(keyboard)
                        .focused($focused)
                }
            }
            .padding(.vertical, Space.sm)
            .padding(.horizontal, Space.md)
            .background(ColorsToken.Background.secondary)
            .overlay(
                RoundedRectangle(cornerRadius: CornerRadiusToken.medium, style: .continuous)
                    .stroke(validationBorderColor(), lineWidth: StrokeWidthToken.thick)
            )
            .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.medium, style: .continuous))

            if let message = validation.message {
                MyonText(message, style: .footnote, color: validation.color)
            }
        }
    }

    private func validationBorderColor() -> Color {
        switch validation {
        case .normal: return focused ? ColorsToken.Brand.primary.opacity(0.6) : ColorsToken.Border.subtle
        case .success: return ColorsToken.State.success
        case .error: return ColorsToken.State.error
        }
    }
}

#if DEBUG
struct MyonTextField_Previews: PreviewProvider {
    static var previews: some View {
        StatefulPreviewWrapper("") { binding in
            VStack(alignment: .leading, spacing: Space.lg) {
                MyonTextField("Email", text: binding, placeholder: "you@example.com")
                MyonTextField("Password", text: binding, placeholder: "••••••••", validation: .error(message: "Invalid password"), isSecure: true)
            }
            .padding(InsetsToken.screen)
        }
    }
}

/// Helper to provide @State bindings in Previews
struct StatefulPreviewWrapper<Value, Content: View>: View {
    @State var value: Value
    var content: (Binding<Value>) -> Content
    init(_ value: Value, content: @escaping (Binding<Value>) -> Content) {
        _value = State(initialValue: value)
        self.content = content
    }
    var body: some View { content($value) }
}
#endif


