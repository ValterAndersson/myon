import SwiftUI

// =============================================================================
// MARK: - ThinkingBubble.swift - Gemini-Style Collapsible Thought Process
// =============================================================================
//
// PURPOSE:
// Single unified UI component for displaying the agent's thinking process.
// Replaces ThoughtTrackView, LiveThoughtTrackView, and StreamOverlay.
//
// UX:
// - Collapsed by default: One line showing current phase or "Show thinking"
// - Tap to expand/collapse
// - Animated sparkle icon while in progress
// - Auto-collapses when complete
//
// USAGE:
//   ThinkingBubble(state: viewModel.thinkingState)
//
// =============================================================================

// MARK: - Main View

struct ThinkingBubble: View {
    @ObservedObject var state: ThinkingProcessState
    
    var body: some View {
        if state.steps.isEmpty {
            EmptyView()
        } else {
            VStack(alignment: .leading, spacing: 0) {
                // Header - always visible
                headerButton
                
                // Expanded content
                if state.isExpanded {
                    expandedContent
                        .transition(.opacity.combined(with: .move(edge: .top)))
                }
            }
            .padding(.vertical, Space.sm)
            .animation(.easeInOut(duration: 0.25), value: state.isExpanded)
        }
    }
    
    // MARK: - Header Button
    
    private var headerButton: some View {
        Button {
            withAnimation(.easeInOut(duration: 0.25)) {
                state.isExpanded.toggle()
            }
        } label: {
            HStack(spacing: Space.sm) {
                // Animated sparkle icon
                SparkleIcon(isAnimating: state.isActive)
                
                // Summary text
                Text(state.summaryText)
                    .font(.system(size: 14, weight: .medium))
                    .foregroundColor(Color.textPrimary)
                
                Spacer()
                
                // Duration (when complete)
                if state.isComplete && state.totalDurationMs > 0 {
                    Text(state.totalDurationText)
                        .font(.system(size: 12))
                        .foregroundColor(Color.textSecondary)
                }
                
                // Chevron
                Image(systemName: state.isExpanded ? "chevron.up" : "chevron.down")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(Color.textSecondary)
            }
            .padding(.horizontal, Space.md)
            .padding(.vertical, Space.sm)
            .background(
                RoundedRectangle(cornerRadius: 20, style: .continuous)
                    .stroke(Color.separatorLine, lineWidth: 1)
            )
        }
        .buttonStyle(PlainButtonStyle())
    }
    
    // MARK: - Expanded Content
    
    private var expandedContent: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Vertical line connecting to steps
            HStack(alignment: .top, spacing: 0) {
                // Connection line
                Rectangle()
                    .fill(Color.separatorLine)
                    .frame(width: 1)
                    .padding(.leading, Space.lg + 6)  // Align with sparkle center
                
                // Steps
                VStack(alignment: .leading, spacing: Space.xs) {
                    ForEach(state.steps) { step in
                        StepRow(step: step, isLast: step.id == state.steps.last?.id)
                    }
                }
                .padding(.leading, Space.md)
            }
            .padding(.top, Space.xs)
        }
    }
}

// MARK: - Step Row

private struct StepRow: View {
    let step: ThinkingStep
    let isLast: Bool
    
    var body: some View {
        VStack(alignment: .leading, spacing: Space.xxs) {
            // Main step header
            HStack(alignment: .top, spacing: Space.sm) {
                // Status indicator
                statusIcon
                    .frame(width: 16, height: 16)
                
                // Content
                VStack(alignment: .leading, spacing: 2) {
                    // Title with phase styling
                    Text(step.title)
                        .font(.system(size: 13, weight: step.status == .active ? .semibold : .medium))
                        .foregroundColor(titleColor)
                        .italic(step.status == .active)
                    
                    // Show tool count summary if we have tool results
                    if !step.toolResults.isEmpty {
                        let completedCount = step.toolResults.filter { $0.isComplete }.count
                        Text("\(completedCount) of \(step.toolResults.count) steps completed")
                            .font(.system(size: 11))
                            .foregroundColor(Color.textSecondary.opacity(0.7))
                    } else if let detail = step.detail {
                        // Fallback to detail if no tool results
                        Text(detail)
                            .font(.system(size: 12))
                            .foregroundColor(Color.textSecondary)
                            .lineLimit(2)
                    }
                }
                
                Spacer()
                
                // Duration (if complete)
                if let durationText = step.durationText {
                    Text(durationText)
                        .font(.system(size: 11))
                        .foregroundColor(Color.textSecondary.opacity(0.7))
                }
            }
            
            // Tool results history (expanded view showing all tools)
            if !step.toolResults.isEmpty {
                VStack(alignment: .leading, spacing: 2) {
                    ForEach(step.toolResults) { toolResult in
                        ToolResultRow(toolResult: toolResult)
                    }
                }
                .padding(.leading, Space.lg + Space.sm)  // Indent under the step
            }
        }
        .padding(.vertical, Space.xxs)
    }
    
    private var statusIcon: some View {
        Group {
            switch step.status {
            case .pending:
                Circle()
                    .stroke(Color.textSecondary.opacity(0.3), lineWidth: 1.5)
                    
            case .active:
                ActiveIndicator()
                
            case .complete:
                Image(systemName: "checkmark")
                    .font(.system(size: 10, weight: .bold))
                    .foregroundColor(.green)
                
            case .error:
                Image(systemName: "exclamationmark.triangle.fill")
                    .font(.system(size: 10))
                    .foregroundColor(.red)
            }
        }
    }
    
    private var titleColor: Color {
        switch step.status {
        case .pending:
            return Color.textSecondary.opacity(0.6)
        case .active:
            return Color.textPrimary
        case .complete:
            return Color.textSecondary
        case .error:
            return .red
        }
    }
}

// MARK: - Tool Result Row

private struct ToolResultRow: View {
    let toolResult: ToolResult
    
    var body: some View {
        HStack(spacing: Space.xs) {
            // Status dot
            Circle()
                .fill(toolResult.isComplete ? Color.green.opacity(0.7) : Color.accent.opacity(0.5))
                .frame(width: 6, height: 6)
            
            // Tool name
            Text(toolResult.displayName)
                .font(.system(size: 11))
                .foregroundColor(Color.textSecondary)
            
            // Arrow and result (if complete)
            if let result = toolResult.result, !result.isEmpty {
                Text("→")
                    .font(.system(size: 10))
                    .foregroundColor(Color.textSecondary.opacity(0.5))
                
                Text(result)
                    .font(.system(size: 11))
                    .foregroundColor(Color.textSecondary.opacity(0.8))
                    .lineLimit(1)
            } else if !toolResult.isComplete {
                // Show spinner for in-progress tools
                ProgressView()
                    .scaleEffect(0.5)
            }
            
            Spacer()
            
            // Duration
            if let durationMs = toolResult.durationMs {
                Text(String(format: "%.1fs", Double(durationMs) / 1000.0))
                    .font(.system(size: 10))
                    .foregroundColor(Color.textSecondary.opacity(0.5))
            }
        }
        .padding(.vertical, 1)
    }
}

// MARK: - Active Indicator (Spinning)

private struct ActiveIndicator: View {
    @State private var isAnimating = false
    
    var body: some View {
        Circle()
            .trim(from: 0, to: 0.7)
            .stroke(Color.accent, lineWidth: 2)
            .rotationEffect(.degrees(isAnimating ? 360 : 0))
            .onAppear {
                withAnimation(.linear(duration: 1).repeatForever(autoreverses: false)) {
                    isAnimating = true
                }
            }
    }
}

// MARK: - Sparkle Icon (Gemini-style)

private struct SparkleIcon: View {
    let isAnimating: Bool
    
    @State private var scale: CGFloat = 1.0
    @State private var rotation: Double = 0
    
    var body: some View {
        Image(systemName: "sparkle")
            .font(.system(size: 14, weight: .medium))
            .foregroundColor(Color.accent)
            .scaleEffect(scale)
            .rotationEffect(.degrees(rotation))
            .onAppear {
                if isAnimating {
                    startAnimation()
                }
            }
            .onChange(of: isAnimating) { _, newValue in
                if newValue {
                    startAnimation()
                } else {
                    stopAnimation()
                }
            }
    }
    
    private func startAnimation() {
        withAnimation(.easeInOut(duration: 0.8).repeatForever(autoreverses: true)) {
            scale = 1.15
        }
        withAnimation(.linear(duration: 3).repeatForever(autoreverses: false)) {
            rotation = 360
        }
    }
    
    private func stopAnimation() {
        withAnimation(.easeOut(duration: 0.3)) {
            scale = 1.0
        }
    }
}

// MARK: - Preview

#if DEBUG
struct ThinkingBubble_Previews: PreviewProvider {
    static var previews: some View {
        VStack(spacing: Space.lg) {
            // In-progress state
            ThinkingBubble(state: {
                let state = ThinkingProcessState()
                // Can't call @MainActor methods in preview directly
                return state
            }())
            
            Spacer()
        }
        .padding()
        .background(Color.bg)
    }
}
#endif
