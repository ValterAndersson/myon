import SwiftUI

// MARK: - Thought Track Models

struct ThoughtStep: Identifiable, Equatable {
    let id: String
    let kind: Kind
    let text: String
    let detail: String?
    let duration: Double?
    let isComplete: Bool
    let timestamp: Date
    
    enum Kind: String {
        case thinking
        case tool
        case insight
        case decision
    }
    
    var icon: String {
        switch kind {
        case .thinking: return "brain.head.profile"
        case .tool: return "gearshape"
        case .insight: return "lightbulb"
        case .decision: return "arrow.triangle.branch"
        }
    }
    
    var completedIcon: String {
        switch kind {
        case .tool: return "checkmark.circle.fill"
        default: return icon
        }
    }
}

struct ThoughtTrack: Identifiable, Equatable {
    let id: String
    var steps: [ThoughtStep]
    var isComplete: Bool
    var summary: String?
    var totalDuration: Double
    
    var toplineText: String {
        if let summary = summary, !summary.isEmpty {
            return summary
        }
        // Auto-generate from steps
        let toolNames = steps.filter { $0.kind == .tool && $0.isComplete }.map { $0.text }
        if toolNames.isEmpty {
            return String(format: "Thought for %.1fs", totalDuration)
        }
        let joined = toolNames.prefix(3).joined(separator: " • ")
        return String(format: "%.1fs • %@", totalDuration, joined)
    }
}

// MARK: - Thought Track View (Expandable)

struct ThoughtTrackView: View {
    let track: ThoughtTrack
    @State private var isExpanded: Bool = false
    
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Topline (always visible)
            Button {
                withAnimation(.easeInOut(duration: 0.2)) {
                    isExpanded.toggle()
                }
            } label: {
                HStack(spacing: Space.sm) {
                    Image(systemName: track.isComplete ? "brain" : "brain.head.profile")
                        .font(.system(size: 14))
                        .foregroundColor(ColorsToken.Text.secondary.opacity(0.7))
                    
                    Text(track.toplineText)
                        .font(.system(size: 13))
                        .foregroundColor(ColorsToken.Text.secondary)
                        .lineLimit(1)
                    
                    Spacer()
                    
                    if track.steps.count > 1 {
                        Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                            .font(.system(size: 11))
                            .foregroundColor(ColorsToken.Text.secondary.opacity(0.5))
                    }
                }
                .padding(.vertical, Space.xs)
            }
            .buttonStyle(.plain)
            
            // Expanded detail
            if isExpanded {
                VStack(alignment: .leading, spacing: Space.xs) {
                    ForEach(track.steps) { step in
                        ThoughtStepRow(step: step)
                    }
                }
                .padding(.leading, Space.lg)
                .padding(.top, Space.xs)
                .transition(.opacity.combined(with: .move(edge: .top)))
            }
        }
        .padding(.horizontal, Space.sm)
        .padding(.vertical, Space.xxs)
        .background(isExpanded ? ColorsToken.Surface.default.opacity(0.3) : Color.clear)
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }
}

// MARK: - Individual Step Row

struct ThoughtStepRow: View {
    let step: ThoughtStep
    
    var body: some View {
        HStack(alignment: .top, spacing: Space.sm) {
            // Status indicator
            ZStack {
                if step.isComplete {
                    Image(systemName: step.completedIcon)
                        .font(.system(size: 11))
                        .foregroundColor(step.kind == .tool ? .green.opacity(0.8) : ColorsToken.Text.secondary.opacity(0.6))
                } else {
                    ProgressView()
                        .scaleEffect(0.5)
                }
            }
            .frame(width: 16, height: 16)
            
            VStack(alignment: .leading, spacing: 2) {
                HStack {
                    Text(step.text)
                        .font(.system(size: 12, weight: step.isComplete ? .regular : .medium))
                        .foregroundColor(step.isComplete ? ColorsToken.Text.secondary : ColorsToken.Text.primary)
                    
                    if let duration = step.duration {
                        Text(String(format: "(%.1fs)", duration))
                            .font(.system(size: 11))
                            .foregroundColor(ColorsToken.Text.secondary.opacity(0.5))
                    }
                }
                
                if let detail = step.detail, !detail.isEmpty {
                    Text(detail)
                        .font(.system(size: 11))
                        .foregroundColor(ColorsToken.Text.secondary.opacity(0.7))
                        .lineLimit(2)
                }
            }
        }
    }
}

// MARK: - Live Thought Track (During Agent Work)

struct LiveThoughtTrackView: View {
    let steps: [ThoughtStep]
    let isActive: Bool
    
    var body: some View {
        VStack(alignment: .leading, spacing: Space.xs) {
            ForEach(steps) { step in
                LiveStepRow(step: step)
            }
            
            if isActive {
                // Show that more is coming
                HStack(spacing: Space.sm) {
                    ProgressView()
                        .scaleEffect(0.5)
                    Text("Working...")
                        .font(.system(size: 12))
                        .foregroundColor(ColorsToken.Text.secondary.opacity(0.7))
                }
                .padding(.leading, Space.sm)
            }
        }
        .padding(.vertical, Space.xs)
    }
}

struct LiveStepRow: View {
    let step: ThoughtStep
    
    var body: some View {
        HStack(alignment: .center, spacing: Space.sm) {
            // Icon with status
            ZStack {
                if step.isComplete {
                    Image(systemName: step.completedIcon)
                        .font(.system(size: 12))
                        .foregroundColor(step.kind == .tool ? .green : ColorsToken.Text.secondary.opacity(0.7))
                } else {
                    ProgressView()
                        .scaleEffect(0.5)
                }
            }
            .frame(width: 18, height: 18)
            
            // Step text
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: Space.xs) {
                    Text(step.text)
                        .font(.system(size: 13, weight: step.isComplete ? .regular : .medium))
                        .foregroundColor(step.isComplete ? ColorsToken.Text.secondary : ColorsToken.Text.primary)
                    
                    if let duration = step.duration {
                        Text(String(format: "%.1fs", duration))
                            .font(.system(size: 11))
                            .foregroundColor(ColorsToken.Text.secondary.opacity(0.5))
                    }
                }
                
                // Show insight/decision text
                if let detail = step.detail, !detail.isEmpty {
                    Text(detail)
                        .font(.system(size: 12, design: .default))
                        .italic()
                        .foregroundColor(ColorsToken.Text.secondary.opacity(0.8))
                        .lineLimit(2)
                }
            }
        }
        .padding(.horizontal, Space.sm)
        .padding(.vertical, Space.xxs)
    }
}

// MARK: - Helper to Build Thought Track from Events

extension ThoughtTrack {
    static func from(events: [WorkspaceEvent]) -> ThoughtTrack? {
        var steps: [ThoughtStep] = []
        var totalDuration: Double = 0
        var lastThinkingStart: Double?
        
        let sortedEvents = events.sorted { ($0.createdAt ?? .distantPast) < ($1.createdAt ?? .distantPast) }
        
        for event in sortedEvents {
            let eventType = event.event.eventType
            let timestamp = event.createdAt ?? Date()
            let ts = event.event.timestamp ?? timestamp.timeIntervalSince1970
            
            switch eventType {
            case .thinking:
                lastThinkingStart = ts
                let text = event.event.content?["text"]?.value as? String ?? "Thinking..."
                // Only add if it has meaningful text
                if text != "Analyzing..." && !text.isEmpty {
                    steps.append(ThoughtStep(
                        id: event.id,
                        kind: .thinking,
                        text: "Thinking",
                        detail: text,
                        duration: nil,
                        isComplete: false,
                        timestamp: timestamp
                    ))
                }
                
            case .thought:
                if let start = lastThinkingStart {
                    let duration = ts - start
                    totalDuration += duration
                    // Update the last thinking step to complete
                    if let idx = steps.lastIndex(where: { $0.kind == .thinking && !$0.isComplete }) {
                        let old = steps[idx]
                        steps[idx] = ThoughtStep(
                            id: old.id,
                            kind: .insight,
                            text: String(format: "Thought for %.1fs", duration),
                            detail: event.event.content?["text"]?.value as? String ?? old.detail,
                            duration: duration,
                            isComplete: true,
                            timestamp: timestamp
                        )
                    }
                    lastThinkingStart = nil
                }
                
            case .toolRunning:
                let toolName = event.event.content?["tool"]?.value as? String ?? "tool"
                steps.append(ThoughtStep(
                    id: event.id,
                    kind: .tool,
                    text: humanReadableToolName(toolName),
                    detail: nil,
                    duration: nil,
                    isComplete: false,
                    timestamp: timestamp
                ))
                
            case .toolComplete:
                let toolName = event.event.content?["tool"]?.value as? String ?? "tool"
                let duration = event.event.content?["duration_s"]?.value as? Double
                let result = event.event.content?["result"]?.value as? String
                
                // Find and update the matching toolRunning step
                if let idx = steps.lastIndex(where: { $0.kind == .tool && $0.text == humanReadableToolName(toolName) && !$0.isComplete }) {
                    let old = steps[idx]
                    steps[idx] = ThoughtStep(
                        id: old.id,
                        kind: .tool,
                        text: old.text,
                        detail: result,
                        duration: duration,
                        isComplete: true,
                        timestamp: timestamp
                    )
                }
                
            default:
                break
            }
        }
        
        guard !steps.isEmpty else { return nil }
        
        // Check if track is complete (no pending steps)
        let isComplete = steps.allSatisfy { $0.isComplete }
        
        return ThoughtTrack(
            id: events.first?.id ?? UUID().uuidString,
            steps: steps,
            isComplete: isComplete,
            summary: nil,
            totalDuration: totalDuration
        )
    }
    
    private static func humanReadableToolName(_ name: String) -> String {
        switch name {
        case "tool_set_context": return "Setting context"
        case "tool_get_user_profile", "tool_fetch_profile": return "Reviewing profile"
        case "tool_get_recent_workouts", "tool_fetch_recent_sessions": return "Checking workouts"
        case "tool_ask_user", "tool_request_clarification": return "Asking question"
        case "tool_create_workout_plan": return "Creating plan"
        case "tool_publish_workout_plan", "tool_publish_cards": return "Publishing"
        case "tool_record_user_info": return "Recording info"
        case "tool_emit_status", "tool_emit_agent_event": return "Logging"
        default: return name.replacingOccurrences(of: "tool_", with: "").replacingOccurrences(of: "_", with: " ").capitalized
        }
    }
}

// MARK: - Preview

#if DEBUG
struct ThoughtTrackView_Previews: PreviewProvider {
    static var previews: some View {
        VStack(spacing: Space.lg) {
            // Complete track (collapsed by default)
            ThoughtTrackView(track: ThoughtTrack(
                id: "1",
                steps: [
                    ThoughtStep(id: "s1", kind: .thinking, text: "Thinking", detail: "Analyzing the user request", duration: 2.1, isComplete: true, timestamp: Date()),
                    ThoughtStep(id: "s2", kind: .tool, text: "Reviewing profile", detail: "Found: intermediate lifter, 3x/week", duration: 0.8, isComplete: true, timestamp: Date()),
                    ThoughtStep(id: "s3", kind: .tool, text: "Checking workouts", detail: "5 recent sessions, mostly full-body", duration: 1.2, isComplete: true, timestamp: Date()),
                    ThoughtStep(id: "s4", kind: .insight, text: "Decision", detail: "Recommending upper/lower split for better recovery", duration: nil, isComplete: true, timestamp: Date()),
                ],
                isComplete: true,
                summary: nil,
                totalDuration: 4.1
            ))
            
            Divider()
            
            // Live track (in progress)
            LiveThoughtTrackView(
                steps: [
                    ThoughtStep(id: "l1", kind: .thinking, text: "Analyzing request", detail: nil, duration: nil, isComplete: true, timestamp: Date()),
                    ThoughtStep(id: "l2", kind: .tool, text: "Reviewing profile", detail: nil, duration: nil, isComplete: false, timestamp: Date()),
                ],
                isActive: true
            )
        }
        .padding()
        .background(ColorsToken.Background.primary)
    }
}
#endif
