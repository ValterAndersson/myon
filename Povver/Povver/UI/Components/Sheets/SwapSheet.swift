import SwiftUI

public struct SwapSheet: View {
    private let onSubmit: (String, [String: String]) -> Void
    @State private var choice: String = "variant"
    @State private var details: String = ""
    public init(onSubmit: @escaping (String, [String: String]) -> Void) { self.onSubmit = onSubmit }
    public var body: some View {
        VStack(alignment: .leading, spacing: Space.md) {
            PovverText("Swap", style: .headline)
            Picker("What to swap", selection: $choice) {
                Text("Muscle group").tag("muscle")
                Text("Equipment").tag("equipment")
                Text("Variant").tag("variant")
                Text("Custom").tag("custom")
            }.pickerStyle(.segmented)
            TextField("Optional details", text: $details)
                .textInputAutocapitalization(.sentences)
                .padding(InsetsToken.symmetric(vertical: Space.sm, horizontal: Space.md))
                .background(ColorsToken.Background.secondary)
                .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.medium, style: .continuous))
            PovverButton("Apply", style: .primary) {
                onSubmit(choice, ["details": details])
            }
        }
        .padding(InsetsToken.screen)
    }
}


