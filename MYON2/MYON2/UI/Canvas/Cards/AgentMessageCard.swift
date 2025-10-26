import SwiftUI

public struct AgentMessageCard: View {
    private let model: CanvasCardModel
    @Environment(\.cardActionHandler) private var handleAction
    
    public init(model: CanvasCardModel) { 
        self.model = model 
    }
    
    public var body: some View {
        CardContainer(status: model.status) {
            VStack(alignment: .leading, spacing: Space.md) {
                // Agent avatar and status indicator
                HStack(spacing: Space.sm) {
                    Image(systemName: "brain")
                        .font(.system(size: 16))
                        .foregroundColor(ColorsToken.Brand.primary)
                    
                    if let status = getStatus() {
                        HStack(spacing: Space.xs) {
                            ProgressView()
                                .scaleEffect(0.7)
                            MyonText(status, style: .caption)
                                .foregroundColor(ColorsToken.Text.secondary)
                        }
                    }
                    
                    Spacer()
                    
                    // Show current time as a placeholder
                    MyonText(Date().formatted(.dateTime.hour().minute()), style: .caption)
                        .foregroundColor(ColorsToken.Text.muted)
                }
                
                // Message text
                if case .agentMessage(let text, _, _) = model.data {
                    MyonText(text, style: .body)
                        .foregroundColor(ColorsToken.Text.primary)
                }
                
                // Tool calls if present
                if case .agentMessage(_, _, let toolCalls) = model.data, !toolCalls.isEmpty {
                    VStack(alignment: .leading, spacing: Space.xs) {
                        ForEach(toolCalls, id: \.name) { tool in
                            HStack(spacing: Space.xs) {
                                Image(systemName: toolIcon(for: tool.name))
                                    .font(.system(size: 12))
                                    .foregroundColor(ColorsToken.Text.secondary)
                                MyonText(tool.name.replacingOccurrences(of: "_", with: " "), style: .caption)
                                    .foregroundColor(ColorsToken.Text.secondary)
                                if tool.status == "complete" {
                                    Image(systemName: "checkmark.circle.fill")
                                        .font(.system(size: 10))
                                        .foregroundColor(ColorsToken.State.success)
                                }
                            }
                            .padding(.vertical, Space.xxs)
                            .padding(.horizontal, Space.xs)
                            .background(ColorsToken.Background.secondary)
                            .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.small))
                        }
                    }
                }
                
                // Action buttons (copy, retry, etc.)
                if !model.actions.isEmpty {
                    HStack(spacing: Space.sm) {
                        ForEach(model.actions, id: \.label) { action in
                            Button(action: { handleAction(action, model) }) {
                                HStack(spacing: Space.xxs) {
                                    if let icon = action.iconSystemName {
                                        Image(systemName: icon)
                                            .font(.system(size: 12))
                                    }
                                    MyonText(action.label, style: .caption)
                                }
                            }
                            .buttonStyle(.bordered)
                            .controlSize(.small)
                        }
                        Spacer()
                    }
                }
            }
        }
    }
    
    private func getStatus() -> String? {
        if case .agentMessage(_, let status, _) = model.data {
            switch status {
            case "thinking": return "Thinking..."
            case "working": return "Working..."
            case "waiting": return "Waiting for response..."
            default: return nil
            }
        }
        return nil
    }
    
    private func toolIcon(for name: String) -> String {
        if name.contains("publish") || name.contains("canvas") {
            return "square.and.arrow.up"
        } else if name.contains("build") || name.contains("generate") {
            return "hammer"
        } else if name.contains("set") || name.contains("context") {
            return "gearshape"
        } else {
            return "wrench"
        }
    }
}
