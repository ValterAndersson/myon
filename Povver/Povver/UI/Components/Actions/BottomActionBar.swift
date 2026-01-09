import SwiftUI

// MARK: - v1.1 Premium Visual System Bottom Action Bar
/// Standard bottom action container for workout screens
/// Handles safe area, consistent padding, and enforces one primary action

public struct BottomActionBar: View {
    private let primaryTitle: String
    private let primaryAction: () -> Void
    private let secondaryTitle: String?
    private let secondaryAction: (() -> Void)?
    private let tertiaryTitle: String?
    private let tertiaryAction: (() -> Void)?
    private let tertiaryIsDestructive: Bool
    private let isPrimaryEnabled: Bool
    
    /// Creates a BottomActionBar with v1.1 styling
    /// - Parameters:
    ///   - primaryTitle: Primary CTA text (e.g., "Finish Workout")
    ///   - primaryAction: Primary CTA action
    ///   - isPrimaryEnabled: Whether primary is enabled
    ///   - secondaryTitle: Optional secondary button (e.g., "Add Exercise")
    ///   - secondaryAction: Secondary action
    ///   - tertiaryTitle: Optional tertiary text button (e.g., "Discard")
    ///   - tertiaryAction: Tertiary action
    ///   - tertiaryIsDestructive: Whether tertiary uses destructive color
    public init(
        primaryTitle: String,
        primaryAction: @escaping () -> Void,
        isPrimaryEnabled: Bool = true,
        secondaryTitle: String? = nil,
        secondaryAction: (() -> Void)? = nil,
        tertiaryTitle: String? = nil,
        tertiaryAction: (() -> Void)? = nil,
        tertiaryIsDestructive: Bool = false
    ) {
        self.primaryTitle = primaryTitle
        self.primaryAction = primaryAction
        self.isPrimaryEnabled = isPrimaryEnabled
        self.secondaryTitle = secondaryTitle
        self.secondaryAction = secondaryAction
        self.tertiaryTitle = tertiaryTitle
        self.tertiaryAction = tertiaryAction
        self.tertiaryIsDestructive = tertiaryIsDestructive
    }
    
    public var body: some View {
        VStack(spacing: Space.md) {
            // Separator at top
            Divider()
                .background(Color.separator)
            
            VStack(spacing: Space.md) {
                // Primary action
                PovverButton(primaryTitle, style: .primary, action: primaryAction)
                    .disabled(!isPrimaryEnabled)
                
                // Secondary action (if present)
                if let secondaryTitle, let secondaryAction {
                    PovverButton(secondaryTitle, style: .secondary, action: secondaryAction)
                }
                
                // Tertiary action (text-only, if present)
                if let tertiaryTitle, let tertiaryAction {
                    Button(action: tertiaryAction) {
                        Text(tertiaryTitle)
                            .textStyle(.body)
                            .foregroundColor(tertiaryIsDestructive ? .destructive : .textSecondary)
                    }
                    .frame(minHeight: 44)
                }
            }
            .padding(.horizontal, Space.lg)
            .padding(.bottom, Space.md)
        }
        .background(Color.surface)
    }
}

// MARK: - Bottom Action Bar Modifier
/// Attaches a BottomActionBar to the bottom of a view with proper safe area handling

public struct BottomActionBarModifier: ViewModifier {
    let bar: BottomActionBar
    
    public func body(content: Content) -> some View {
        content
            .safeAreaInset(edge: .bottom) {
                bar
            }
    }
}

public extension View {
    /// Attaches a BottomActionBar to the view
    func bottomActionBar(_ bar: BottomActionBar) -> some View {
        modifier(BottomActionBarModifier(bar: bar))
    }
}

#if DEBUG
struct BottomActionBar_Previews: PreviewProvider {
    static var previews: some View {
        VStack {
            Spacer()
            Text("Workout Content")
            Spacer()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.bg)
        .bottomActionBar(
            BottomActionBar(
                primaryTitle: "Finish Workout",
                primaryAction: {},
                secondaryTitle: "Add Exercise",
                secondaryAction: {},
                tertiaryTitle: "Discard Workout",
                tertiaryAction: {},
                tertiaryIsDestructive: true
            )
        )
    }
}
#endif
