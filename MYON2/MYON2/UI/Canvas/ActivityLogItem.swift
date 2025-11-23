import SwiftUI

/// Individual activity log item for the stream overlay
/// Displays event with icon, text, and optional duration in a Cursor-like format
struct ActivityLogItem: View {
    let event: StreamEvent
    let userPrompt: String?
    @State private var animationRotation: Double = 0
    
    var body: some View {
        HStack(alignment: .top, spacing: Space.md) {
            // Icon
            iconView
                .frame(width: IconSizeToken.md, height: IconSizeToken.md)
            
            // Content
            VStack(alignment: .leading, spacing: Space.xxs) {
                HStack(spacing: Space.xs) {
                    Text(displayLabel)
                        .font(.system(size: 15, weight: .regular))
                        .foregroundColor(ColorsToken.Text.inverse)
                    
                    if let duration = event.durationText {
                        Text(duration)
                            .font(.system(size: 13, weight: .regular))
                            .foregroundColor(ColorsToken.Text.inverse.opacity(0.6))
                    }
                }
                
                // Show additional text for agent responses or messages
                if let responseText = responseText {
                    Text(responseText)
                        .font(.system(size: 14, weight: .regular))
                        .foregroundColor(ColorsToken.Text.inverse.opacity(0.9))
                        .lineLimit(nil)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            
            Spacer(minLength: 0)
        }
        .padding(.vertical, Space.xs)
        .onAppear {
            if event.shouldAnimate {
                withAnimation(.linear(duration: 2).repeatForever(autoreverses: false)) {
                    animationRotation = 360
                }
            }
        }
    }
    
    // MARK: - Computed Properties
    
    @ViewBuilder
    private var iconView: some View {
        let iconName = event.iconName
        
        if event.isInProgress {
            // Spinning gear for in-progress
            Image(systemName: iconName)
                .font(.system(size: IconSizeToken.md))
                .foregroundColor(ColorsToken.Text.inverse.opacity(0.8))
                .rotationEffect(.degrees(animationRotation))
        } else if event.isCompleted {
            // Static icon with subtle highlight for completed
            Image(systemName: iconName)
                .font(.system(size: IconSizeToken.md))
                .foregroundColor(ColorsToken.Brand.accent100)
        } else if event.eventType == .userPrompt {
            // User icon
            Image(systemName: iconName)
                .font(.system(size: IconSizeToken.md))
                .foregroundColor(ColorsToken.Text.inverse)
        } else if event.eventType == .error {
            // Error icon
            Image(systemName: iconName)
                .font(.system(size: IconSizeToken.md))
                .foregroundColor(ColorsToken.State.error)
        } else {
            // Default icon
            Image(systemName: iconName)
                .font(.system(size: IconSizeToken.md))
                .foregroundColor(ColorsToken.Text.inverse.opacity(0.7))
        }
    }
    
    private var displayLabel: String {
        if event.eventType == .userPrompt {
            return userPrompt ?? "User prompt"
        }
        
        switch event.eventType {
        case .thinking:
            return "Thinking"
        case .thought:
            return "Thought for"
        case .toolRunning:
            return event.displayText
        case .toolComplete:
            return "Looked at \(event.displayText.lowercased())"
        case .message, .agentResponse:
            return "" // Response text shown separately
        case .error:
            return "Error: \(event.displayText)"
        default:
            return event.displayText
        }
    }
    
    private var responseText: String? {
        if event.eventType == .message || event.eventType == .agentResponse {
            return event.displayText
        }
        return nil
    }
}

// MARK: - Preview

#if DEBUG
struct ActivityLogItem_Previews: PreviewProvider {
    static var previews: some View {
        ZStack {
            Color.black.opacity(0.85)
                .ignoresSafeArea()
            
            VStack(alignment: .leading, spacing: Space.md) {
                ActivityLogItem(
                    event: StreamEvent(
                        type: "userPrompt",
                        agent: "user",
                        content: [:],
                        timestamp: Date().timeIntervalSince1970,
                        metadata: nil
                    ),
                    userPrompt: "Create a workout plan for hypertrophy"
                )
                
                ActivityLogItem(
                    event: StreamEvent(
                        type: "thinking",
                        agent: "orchestrator",
                        content: ["text": AnyCodable("Analyzing request...")],
                        timestamp: Date().timeIntervalSince1970,
                        metadata: nil
                    ),
                    userPrompt: nil
                )
                
                ActivityLogItem(
                    event: StreamEvent(
                        type: "thought",
                        agent: "orchestrator",
                        content: [:],
                        timestamp: Date().timeIntervalSince1970 + 4.3,
                        metadata: ["start_time": AnyCodable(Date().timeIntervalSince1970)]
                    ),
                    userPrompt: nil
                )
                
                ActivityLogItem(
                    event: StreamEvent(
                        type: "toolRunning",
                        agent: "orchestrator",
                        content: ["tool_name": AnyCodable("activity_history")],
                        timestamp: Date().timeIntervalSince1970,
                        metadata: nil
                    ),
                    userPrompt: nil
                )
                
                ActivityLogItem(
                    event: StreamEvent(
                        type: "toolComplete",
                        agent: "orchestrator",
                        content: ["tool_name": AnyCodable("activity_history")],
                        timestamp: Date().timeIntervalSince1970 + 1.8,
                        metadata: ["start_time": AnyCodable(Date().timeIntervalSince1970)]
                    ),
                    userPrompt: nil
                )
                
                ActivityLogItem(
                    event: StreamEvent(
                        type: "agentResponse",
                        agent: "orchestrator",
                        content: ["text": AnyCodable("Based on your activity history, I'll create a 4-day upper/lower split focused on hypertrophy with progressive overload.")],
                        timestamp: Date().timeIntervalSince1970,
                        metadata: nil
                    ),
                    userPrompt: nil
                )
            }
            .padding(Space.lg)
        }
    }
}
#endif

