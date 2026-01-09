import SwiftUI

// MARK: - v1.1 Premium Visual System List Row
/// Consistent list row with standard anatomy: leading icon -> title -> subtitle -> trailing accessory
/// 16pt insets, 44pt minimum height for tap targets

public enum ListRowAccessory {
    case none
    case chevron
    case toggle(Binding<Bool>)
    case value(String)
    case custom(AnyView)
}

public struct ListRow<Leading: View>: View {
    private let title: String
    private let subtitle: String?
    private let leading: Leading
    private let accessory: ListRowAccessory
    private let action: (() -> Void)?
    
    /// Creates a ListRow with v1.1 styling
    /// - Parameters:
    ///   - title: Primary text
    ///   - subtitle: Optional secondary text
    ///   - leading: Optional leading view (icon/avatar)
    ///   - accessory: Trailing accessory (chevron, toggle, value, etc.)
    ///   - action: Optional tap action (adds button behavior)
    public init(
        title: String,
        subtitle: String? = nil,
        accessory: ListRowAccessory = .none,
        action: (() -> Void)? = nil,
        @ViewBuilder leading: () -> Leading = { EmptyView() }
    ) {
        self.title = title
        self.subtitle = subtitle
        self.leading = leading()
        self.accessory = accessory
        self.action = action
    }
    
    public var body: some View {
        if let action = action {
            Button(action: action) {
                rowContent
            }
            .buttonStyle(ListRowButtonStyle())
        } else {
            rowContent
        }
    }
    
    private var rowContent: some View {
        HStack(spacing: Space.md) {
            // Leading
            leading
            
            // Title + Subtitle
            VStack(alignment: .leading, spacing: Space.xs) {
                Text(title)
                    .textStyle(.body)
                    .foregroundColor(.textPrimary)
                
                if let subtitle {
                    Text(subtitle)
                        .textStyle(.secondary)
                        .foregroundColor(.textSecondary)
                }
            }
            
            Spacer(minLength: Space.sm)
            
            // Trailing Accessory
            accessoryView
        }
        .padding(.horizontal, Space.lg)
        .padding(.vertical, Space.md)
        .frame(minHeight: 44) // iOS tap target minimum
        .contentShape(Rectangle())
    }
    
    @ViewBuilder
    private var accessoryView: some View {
        switch accessory {
        case .none:
            EmptyView()
        case .chevron:
            Image(systemName: "chevron.right")
                .font(.system(size: 14, weight: .semibold))
                .foregroundColor(.textTertiary)
        case .toggle(let binding):
            Toggle("", isOn: binding)
                .labelsHidden()
                .tint(.accent)
        case .value(let text):
            Text(text)
                .textStyle(.secondary)
                .foregroundColor(.textSecondary)
        case .custom(let view):
            view
        }
    }
}

// MARK: - Convenience initializer without leading view
extension ListRow where Leading == EmptyView {
    public init(
        title: String,
        subtitle: String? = nil,
        accessory: ListRowAccessory = .none,
        action: (() -> Void)? = nil
    ) {
        self.init(title: title, subtitle: subtitle, accessory: accessory, action: action, leading: { EmptyView() })
    }
}

// MARK: - List Row Button Style
private struct ListRowButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .background(configuration.isPressed ? Color.surfaceElevated : Color.clear)
            .animation(.easeInOut(duration: MotionToken.fast), value: configuration.isPressed)
    }
}

// MARK: - Legacy initializer for backward compatibility
extension ListRow {
    @available(*, deprecated, message: "Use new ListRow initializer with accessory parameter")
    public init<Trailing: View>(
        title: String,
        subtitle: String? = nil,
        @ViewBuilder leading: () -> Leading,
        @ViewBuilder trailing: () -> Trailing
    ) where Trailing: View {
        self.title = title
        self.subtitle = subtitle
        self.leading = leading()
        self.accessory = .custom(AnyView(trailing()))
        self.action = nil
    }
}

#if DEBUG
struct ListRow_Previews: PreviewProvider {
    static var previews: some View {
        VStack(spacing: 0) {
            ListRow(
                title: "Settings",
                subtitle: "Configure app preferences",
                accessory: .chevron,
                action: {},
                leading: {
                    Image(systemName: "gearshape.fill")
                        .foregroundColor(.accent)
                }
            )
            
            Divider().padding(.leading, Space.lg)
            
            ListRow(
                title: "Notifications",
                accessory: .toggle(.constant(true)),
                leading: {
                    Image(systemName: "bell.fill")
                        .foregroundColor(.accent)
                }
            )
            
            Divider().padding(.leading, Space.lg)
            
            ListRow(
                title: "Version",
                accessory: .value("1.1.0")
            )
        }
        .background(Color.surface)
        .previewLayout(.sizeThatFits)
    }
}
#endif
