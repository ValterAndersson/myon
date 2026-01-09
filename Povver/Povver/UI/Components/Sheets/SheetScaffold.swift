import SwiftUI

// MARK: - v1.1 Premium Visual System Sheet Scaffold
/// Standardized sheet/modal container with consistent toolbar and background
/// Cancel (text, left), Done/Save (accent text, right)

public struct SheetScaffold<Content: View>: View {
    private let title: String?
    private let cancelTitle: String
    private let doneTitle: String?
    private let onCancel: () -> Void
    private let onDone: (() -> Void)?
    private let isDoneEnabled: Bool
    private let content: Content
    
    /// Creates a SheetScaffold with v1.1 styling
    /// - Parameters:
    ///   - title: Optional navigation bar title
    ///   - cancelTitle: Cancel button text (default "Cancel")
    ///   - doneTitle: Done button text (nil hides the button)
    ///   - isDoneEnabled: Whether the done button is enabled
    ///   - onCancel: Cancel action (dismiss sheet)
    ///   - onDone: Done action
    ///   - content: Sheet content
    public init(
        title: String? = nil,
        cancelTitle: String = "Cancel",
        doneTitle: String? = "Done",
        isDoneEnabled: Bool = true,
        onCancel: @escaping () -> Void,
        onDone: (() -> Void)? = nil,
        @ViewBuilder content: () -> Content
    ) {
        self.title = title
        self.cancelTitle = cancelTitle
        self.doneTitle = doneTitle
        self.onCancel = onCancel
        self.onDone = onDone
        self.isDoneEnabled = isDoneEnabled
        self.content = content()
    }
    
    public var body: some View {
        NavigationStack {
            content
                .background(Color.surfaceElevated)
                .navigationTitle(title ?? "")
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .cancellationAction) {
                        Button(cancelTitle, action: onCancel)
                            .foregroundColor(.textPrimary)
                    }
                    
                    if let doneTitle, let onDone {
                        ToolbarItem(placement: .confirmationAction) {
                            Button(doneTitle, action: onDone)
                                .foregroundColor(isDoneEnabled ? .accent : .textTertiary)
                                .disabled(!isDoneEnabled)
                        }
                    }
                }
        }
        .presentationDragIndicator(.visible)
        .presentationBackground(Color.surfaceElevated)
    }
}

// MARK: - Sheet Scaffold with destructive action
extension SheetScaffold {
    /// Creates a SheetScaffold with a destructive done action
    public static func destructive(
        title: String? = nil,
        cancelTitle: String = "Cancel",
        destructiveTitle: String = "Delete",
        isDoneEnabled: Bool = true,
        onCancel: @escaping () -> Void,
        onDestructive: @escaping () -> Void,
        @ViewBuilder content: () -> Content
    ) -> some View {
        NavigationStack {
            content()
                .background(Color.surfaceElevated)
                .navigationTitle(title ?? "")
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .cancellationAction) {
                        Button(cancelTitle, action: onCancel)
                            .foregroundColor(.textPrimary)
                    }
                    
                    ToolbarItem(placement: .confirmationAction) {
                        Button(destructiveTitle, action: onDestructive)
                            .foregroundColor(isDoneEnabled ? .destructive : .textTertiary)
                            .disabled(!isDoneEnabled)
                    }
                }
        }
        .presentationDragIndicator(.visible)
        .presentationBackground(Color.surfaceElevated)
    }
}

// MARK: - Sheet Section (for grouping content)
public struct SheetSection<Content: View>: View {
    private let header: String?
    private let footer: String?
    private let content: Content
    
    public init(
        header: String? = nil,
        footer: String? = nil,
        @ViewBuilder content: () -> Content
    ) {
        self.header = header
        self.footer = footer
        self.content = content()
    }
    
    public var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            if let header {
                Text(header.uppercased())
                    .textStyle(.caption)
                    .foregroundColor(.textSecondary)
                    .padding(.horizontal, Space.lg)
                    .padding(.bottom, Space.sm)
            }
            
            VStack(spacing: 0) {
                content
            }
            .background(Color.surface)
            .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.radiusControl, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: CornerRadiusToken.radiusControl, style: .continuous)
                    .stroke(Color.separator, lineWidth: StrokeWidthToken.hairline)
            )
            .padding(.horizontal, Space.lg)
            
            if let footer {
                Text(footer)
                    .textStyle(.caption)
                    .foregroundColor(.textTertiary)
                    .padding(.horizontal, Space.lg)
                    .padding(.top, Space.sm)
            }
        }
        .padding(.vertical, Space.sm)
    }
}

#if DEBUG
struct SheetScaffold_Previews: PreviewProvider {
    static var previews: some View {
        SheetScaffold(
            title: "Edit Height",
            doneTitle: "Save",
            onCancel: {},
            onDone: {}
        ) {
            ScrollView {
                VStack(spacing: Space.lg) {
                    SheetSection(header: "Measurement") {
                        ListRow(
                            title: "Height",
                            accessory: .value("170 cm")
                        )
                    }
                    
                    SheetSection(footer: "Your height is used for BMI calculations.") {
                        ListRow(
                            title: "Use metric",
                            accessory: .toggle(.constant(true))
                        )
                    }
                }
                .padding(.top, Space.lg)
            }
        }
    }
}
#endif
