import SwiftUI

struct AgentMessageCard: View {
    let model: CanvasCardModel
    
    private var agentMessage: AgentMessage? {
        guard case .agentMessage(let message) = model.data else { return nil }
        return message
    }
    
    var body: some View {
        VStack(alignment: .leading, spacing: Space.md) {
            // Header with icon and status
            HStack(spacing: Space.sm) {
                Image(systemName: iconName)
                    .font(.system(size: 16))
                    .foregroundColor(ColorsToken.Brand.primary)
                    .rotationEffect(shouldAnimate ? .degrees(360) : .zero)
                    .animation(shouldAnimate ? Animation.linear(duration: 1).repeatForever(autoreverses: false) : .default, value: shouldAnimate)
                
                Text(agentMessage?.status ?? "Working...")
                    .font(.body)
                    .foregroundColor(ColorsToken.Text.primary)
                
                Spacer()
                
                Text(Date().formatted(.dateTime.hour().minute()))
                    .font(.caption)
                    .foregroundColor(ColorsToken.Text.secondary)
            }
            
            // Message content
            if let message = agentMessage?.message, !message.isEmpty {
                Text(message)
                    .font(.body)
                    .foregroundColor(ColorsToken.Text.primary)
                    .padding(.top, Space.xs)
            }
            
            // Tool calls
            if let toolCalls = agentMessage?.toolCalls, !toolCalls.isEmpty {
                VStack(alignment: .leading, spacing: Space.xs) {
                    ForEach(Array(toolCalls.enumerated()), id: \.offset) { _, tool in
                        HStack(spacing: Space.xs) {
                            Image(systemName: "wrench.and.screwdriver")
                                .font(.system(size: 12))
                                .foregroundColor(ColorsToken.Text.secondary)
                            
                            Text(tool.displayName)
                                .font(.caption)
                                .foregroundColor(ColorsToken.Text.secondary)
                            
                            if let duration = tool.duration {
                                Text("(\(duration))")
                                    .font(.caption)
                                    .foregroundColor(ColorsToken.Text.secondary.opacity(0.7))
                            }
                        }
                    }
                }
                .padding(.top, Space.xs)
            }
            
            // Thinking steps
            if let thoughts = agentMessage?.thoughts, !thoughts.isEmpty {
                VStack(alignment: .leading, spacing: Space.xs) {
                    ForEach(Array(thoughts.enumerated()), id: \.offset) { index, thought in
                        HStack(alignment: .top, spacing: Space.xs) {
                            Text("•")
                                .font(.caption)
                                .foregroundColor(ColorsToken.Text.secondary)
                            
                            Text(thought)
                                .font(.caption)
                                .foregroundColor(ColorsToken.Text.secondary)
                        }
                    }
                }
                .padding(.top, Space.xs)
            }
        }
        .padding(Space.md)
        .background(ColorsToken.Background.secondary)
        .cornerRadius(CornerRadiusToken.medium)
    }
    
    private var iconName: String {
        switch agentMessage?.type {
        case "thinking":
            return "brain"
        case "tool_running":
            return "gearshape"
        case "tool_complete":
            return "checkmark.circle"
        case "status":
            return "info.circle"
        case "error":
            return "exclamationmark.triangle"
        default:
            return "circle"
        }
    }
    
    private var shouldAnimate: Bool {
        return agentMessage?.type == "thinking" || agentMessage?.type == "tool_running"
    }
}
