import SwiftUI

// MARK: - v1.1 Premium Visual System Empty State
/// Consistent empty state view with icon, title, body, and optional primary action

public struct EmptyState: View {
    private let icon: Image
    private let title: String
    private let message: String?
    private let actionTitle: String?
    private let action: (() -> Void)?

    /// Creates an EmptyState with v1.1 styling
    /// - Parameters:
    ///   - icon: SF Symbol image
    ///   - title: Main heading
    ///   - message: Optional body text
    ///   - actionTitle: Optional primary button title
    ///   - action: Button action
    public init(
        icon: Image = Image(systemName: "tray"),
        title: String,
        message: String? = nil,
        actionTitle: String? = nil,
        action: (() -> Void)? = nil
    ) {
        self.icon = icon
        self.title = title
        self.message = message
        self.actionTitle = actionTitle
        self.action = action
    }
    
    /// Convenience initializer with SF Symbol name
    public init(
        systemName: String,
        title: String,
        message: String? = nil,
        actionTitle: String? = nil,
        action: (() -> Void)? = nil
    ) {
        self.icon = Image(systemName: systemName)
        self.title = title
        self.message = message
        self.actionTitle = actionTitle
        self.action = action
    }
    
    /// Legacy initializer for backward compatibility
    public init(
        title: String,
        message: String? = nil,
        actionTitle: String? = nil,
        action: (() -> Void)? = nil
    ) {
        self.icon = Image(systemName: "tray")
        self.title = title
        self.message = message
        self.actionTitle = actionTitle
        self.action = action
    }

    public var body: some View {
        VStack(spacing: Space.lg) {
            // Icon (44-56pt)
            icon
                .resizable()
                .scaledToFit()
                .frame(width: 48, height: 48)
                .foregroundColor(.textTertiary)
            
            VStack(spacing: Space.sm) {
                // Title (sectionHeader)
                Text(title)
                    .textStyle(.sectionHeader)
                    .foregroundColor(.textPrimary)
                    .multilineTextAlignment(.center)
                
                // Body (secondary)
                if let message {
                    Text(message)
                        .textStyle(.secondary)
                        .foregroundColor(.textSecondary)
                        .multilineTextAlignment(.center)
                }
            }
            
            // Primary action (max one)
            if let actionTitle, let action {
                PovverButton(actionTitle, style: .primary, action: action)
                    .frame(maxWidth: 280)
                    .padding(.top, Space.sm)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(InsetsToken.screen)
    }
}

#if DEBUG
struct EmptyState_Previews: PreviewProvider {
    static var previews: some View {
        VStack(spacing: Space.xxl) {
            EmptyState(
                systemName: "dumbbell.fill",
                title: "No Routines Yet",
                message: "Create a routine to organize your training programs.",
                actionTitle: "Create Routine",
                action: {}
            )
            
            EmptyState(
                systemName: "clock.arrow.circlepath",
                title: "No History",
                message: "Complete a workout to see it here."
            )
        }
    }
}
#endif
