import SwiftUI

public struct RefineSheet: View {
    @Binding private var text: String
    private let onSubmit: (String) -> Void
    private let chips: [String]
    public init(text: Binding<String>, chips: [String] = ["Shorter", "More detail", "Simpler"], onSubmit: @escaping (String) -> Void) {
        self._text = text
        self.chips = chips
        self.onSubmit = onSubmit
    }
    public var body: some View {
        VStack(alignment: .leading, spacing: Space.md) {
            PovverText("Refine", style: .headline)
            HStack(spacing: Space.sm) {
                ForEach(chips, id: \.self) { c in
                    Button(c) { text = c }
                        .buttonStyle(.bordered)
                }
            }
            TextField("Add context", text: $text)
                .textInputAutocapitalization(.sentences)
                .padding(InsetsToken.symmetric(vertical: Space.sm, horizontal: Space.md))
                .background(Color.surfaceElevated)
                .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.medium, style: .continuous))
            PovverButton("Submit", style: .primary) { onSubmit(text) }
        }
        .padding(InsetsToken.screen)
    }
}


