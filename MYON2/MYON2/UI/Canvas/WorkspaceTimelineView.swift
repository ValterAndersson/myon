import SwiftUI

struct TimelineClarificationPrompt: Identifiable {
    let id: String
    let question: String
}

// MARK: - Timeline Item Types
private enum TimelineItemKind {
    case userMessage(text: String)
    case thoughtTrack(ThoughtTrack)           // Completed thought track (expandable)
    case liveThoughtTrack([ThoughtStep])      // In-progress thought track
    case agentResponse(text: String)
    case artifact(CanvasCardModel)
    case clarification(TimelineClarificationPrompt)
    case status(text: String)
    case error(text: String)
}

private struct TimelineItem: Identifiable {
    let id: String
    let timestamp: Date
    let kind: TimelineItemKind
}

// MARK: - Main View
struct WorkspaceTimelineView: View {
    let events: [WorkspaceEvent]
    let embeddedCards: [CanvasCardModel]
    let syntheticClarification: TimelineClarificationPrompt?
    let answeredClarifications: Set<String>
    let onClarificationSubmit: (String, String, String) -> Void
    let onClarificationSkip: (String, String) -> Void
    
    @State private var autoScroll = true
    @State private var scrollProxy: ScrollViewProxy?
    @State private var responses: [String: String] = [:]
    @State private var collapsedTools = true
    
    typealias ClarificationPrompt = TimelineClarificationPrompt
    
    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 0) {
                    // Header
                    workspaceHeader
                    
                    // Synthetic clarification at top if pending
                    if let syntheticClarification,
                       !answeredClarifications.contains(syntheticClarification.id) {
                        clarificationBubble(for: syntheticClarification)
                            .id(syntheticClarification.id + "-synthetic")
                            .padding(.bottom, Space.md)
                    }
                    
                    // Timeline items
                    ForEach(timelineItems) { item in
                        timelineItemView(for: item)
                            .id(item.id)
                            .transition(.asymmetric(
                                insertion: .opacity.combined(with: .move(edge: .bottom)),
                                removal: .opacity
                            ))
                    }
                }
                .padding(.horizontal, Space.lg)
                .padding(.bottom, Space.xxl)
            }
            .background(ColorsToken.Background.primary)
            .onAppear { scrollProxy = proxy }
            .onChange(of: timelineItems.count) { _ in
                guard autoScroll, let id = timelineItems.last?.id else { return }
                withAnimation(.easeOut(duration: 0.3)) {
                    proxy.scrollTo(id, anchor: .bottom)
                }
            }
            .gesture(DragGesture().onChanged { _ in autoScroll = false })
            .overlay(alignment: .bottomTrailing) {
                if !autoScroll {
                    jumpToLatestButton
                }
            }
        }
    }
    
    // MARK: - Header
    private var workspaceHeader: some View {
        HStack {
            VStack(alignment: .leading, spacing: Space.xxs) {
                Text("Canvas")
                    .font(.system(size: 18, weight: .bold))
                    .foregroundColor(ColorsToken.Text.primary)
                Text("Your AI coaching session")
                    .font(.system(size: 13))
                    .foregroundColor(ColorsToken.Text.secondary)
            }
            Spacer()
            if hasActiveThinking {
                thinkingIndicator
            }
        }
        .padding(.vertical, Space.md)
    }
    
    private var hasActiveThinking: Bool {
        events.contains { $0.event.eventType == .thinking || $0.event.eventType == .toolRunning }
    }
    
    private var thinkingIndicator: some View {
        HStack(spacing: Space.xs) {
            ProgressView()
                .scaleEffect(0.7)
            Text("Working...")
                .font(.system(size: 12))
                .foregroundColor(ColorsToken.Text.secondary)
        }
        .padding(.horizontal, Space.sm)
        .padding(.vertical, Space.xxs)
        .background(ColorsToken.Surface.default.opacity(0.8))
        .clipShape(Capsule())
    }
    
    private var jumpToLatestButton: some View {
        Button {
            autoScroll = true
            if let id = timelineItems.last?.id {
                withAnimation { scrollProxy?.scrollTo(id, anchor: .bottom) }
            }
        } label: {
            HStack(spacing: Space.xs) {
                Image(systemName: "arrow.down")
                Text("Latest")
            }
            .font(.system(size: 13, weight: .medium))
            .foregroundColor(.white)
            .padding(.horizontal, Space.md)
            .padding(.vertical, Space.sm)
            .background(ColorsToken.Brand.primary)
            .clipShape(Capsule())
            .shadow(color: .black.opacity(0.15), radius: 8, y: 4)
        }
        .padding(Space.md)
    }
    
    // MARK: - Timeline Item View
    @ViewBuilder
    private func timelineItemView(for item: TimelineItem) -> some View {
        switch item.kind {
        case .userMessage(let text):
            userMessageBubble(text: text, timestamp: item.timestamp)
        case .thoughtTrack(let track):
            ThoughtTrackView(track: track)
        case .liveThoughtTrack(let steps):
            LiveThoughtTrackView(steps: steps, isActive: true)
        case .agentResponse(let text):
            agentResponseBubble(text: text, timestamp: item.timestamp)
        case .artifact(let card):
            artifactCard(for: card)
        case .clarification(let prompt):
            if !answeredClarifications.contains(prompt.id) {
                clarificationBubble(for: prompt)
            }
        case .status(let text):
            statusRow(text: text)
        case .error(let text):
            errorRow(text: text)
        }
    }
    
    // MARK: - User Message
    private func userMessageBubble(text: String, timestamp: Date) -> some View {
        HStack(alignment: .bottom, spacing: Space.sm) {
            Spacer(minLength: 60)
            VStack(alignment: .trailing, spacing: Space.xxs) {
                Text(text)
                    .font(.system(size: 15))
                    .foregroundColor(.white)
                    .padding(.horizontal, Space.md)
                    .padding(.vertical, Space.sm)
                    .background(ColorsToken.Brand.primary)
                    .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
                    .clipShape(BubbleShape(isUser: true))
                
                Text(Self.timeFormatter.string(from: timestamp))
                    .font(.system(size: 11))
                    .foregroundColor(ColorsToken.Text.secondary.opacity(0.6))
            }
        }
        .padding(.vertical, Space.sm)
    }
    
    // MARK: - Agent Response
    private func agentResponseBubble(text: String, timestamp: Date) -> some View {
        HStack(alignment: .bottom, spacing: Space.sm) {
            VStack(alignment: .leading, spacing: Space.xxs) {
                HStack(spacing: Space.xs) {
                    Image(systemName: "brain")
                        .font(.system(size: 12))
                        .foregroundColor(ColorsToken.Brand.primary)
                    Text("Coach")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundColor(ColorsToken.Text.secondary)
                }
                
                Text(text)
                    .font(.system(size: 15))
                    .foregroundColor(ColorsToken.Text.primary)
                    .padding(.horizontal, Space.md)
                    .padding(.vertical, Space.sm)
                    .background(ColorsToken.Surface.default)
                    .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
                
                Text(Self.timeFormatter.string(from: timestamp))
                    .font(.system(size: 11))
                    .foregroundColor(ColorsToken.Text.secondary.opacity(0.6))
            }
            Spacer(minLength: 60)
        }
        .padding(.vertical, Space.sm)
    }
    
    // MARK: - Thinking Row (Subtle)
    private func thinkingRow(text: String, duration: Double?) -> some View {
        HStack(spacing: Space.sm) {
            Image(systemName: "brain.head.profile")
                .font(.system(size: 14))
                .foregroundColor(ColorsToken.Text.secondary.opacity(0.6))
            
            if let duration {
                Text(String(format: "Thought for %.1fs", duration))
                    .font(.system(size: 13, weight: .medium))
                    .foregroundColor(ColorsToken.Text.secondary)
            } else {
                HStack(spacing: Space.xs) {
                    Text(text.isEmpty ? "Thinking..." : text)
                        .font(.system(size: 13))
                        .foregroundColor(ColorsToken.Text.secondary)
                    ProgressView()
                        .scaleEffect(0.6)
                }
            }
        }
        .padding(.vertical, Space.xs)
        .padding(.leading, Space.sm)
    }
    
    // MARK: - Tool Activity Row (Collapsible)
    private func toolActivityRow(name: String, result: String?, duration: Double?) -> some View {
        HStack(spacing: Space.sm) {
            Image(systemName: result != nil ? "checkmark.circle.fill" : "gearshape")
                .font(.system(size: 12))
                .foregroundColor(result != nil ? .green.opacity(0.7) : ColorsToken.Text.secondary.opacity(0.5))
            
            VStack(alignment: .leading, spacing: 2) {
                Text(humanReadableToolName(name))
                    .font(.system(size: 12))
                    .foregroundColor(ColorsToken.Text.secondary)
                if let result, !result.isEmpty {
                    Text(result)
                        .font(.system(size: 11))
                        .foregroundColor(ColorsToken.Text.secondary.opacity(0.7))
                        .lineLimit(1)
                }
            }
            
            Spacer()
            
            if let duration {
                Text(String(format: "%.1fs", duration))
                    .font(.system(size: 11))
                    .foregroundColor(ColorsToken.Text.secondary.opacity(0.5))
            }
        }
        .padding(.vertical, Space.xxs)
        .padding(.horizontal, Space.sm)
        .background(ColorsToken.Surface.default.opacity(0.3))
        .clipShape(RoundedRectangle(cornerRadius: 6))
        .padding(.leading, Space.lg)
    }
    
    // MARK: - Artifact Card (Full Width, Prominent)
    private func artifactCard(for card: CanvasCardModel) -> some View {
        VStack(alignment: .leading, spacing: Space.xs) {
            // Artifact label
            HStack(spacing: Space.xs) {
                Image(systemName: artifactIcon(for: card))
                    .font(.system(size: 12))
                    .foregroundColor(ColorsToken.Brand.primary)
                Text(artifactLabel(for: card))
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(ColorsToken.Brand.primary)
            }
            .padding(.leading, Space.xs)
            
            // The actual card
            cardView(for: card)
        }
        .padding(.vertical, Space.md)
    }
    
    private func artifactIcon(for card: CanvasCardModel) -> String {
        switch card.data {
        case .sessionPlan: return "figure.strengthtraining.traditional"
        case .visualization: return "chart.bar"
        case .list: return "list.bullet"
        case .agentStream: return "brain"
        case .routineOverview: return "calendar"
        default: return "doc.text"
        }
    }
    
    private func artifactLabel(for card: CanvasCardModel) -> String {
        switch card.data {
        case .sessionPlan: return "Workout Plan"
        case .visualization: return "Analysis"
        case .list: return "Recommendations"
        case .inlineInfo: return "Note"
        case .agentStream: return "Processing"
        case .routineOverview: return "Routine"
        default: return "Update"
        }
    }
    
    // MARK: - Clarification Bubble
    private func clarificationBubble(for prompt: TimelineClarificationPrompt) -> some View {
        VStack(alignment: .leading, spacing: Space.sm) {
            HStack(spacing: Space.xs) {
                Image(systemName: "questionmark.circle.fill")
                    .foregroundColor(ColorsToken.Brand.primary)
                Text("Coach needs input")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(ColorsToken.Brand.primary)
            }
            
            Text(prompt.question)
                .font(.system(size: 15))
                .foregroundColor(ColorsToken.Text.primary)
            
            TextField("Type your answer…", text: Binding(
                get: { responses[prompt.id] ?? "" },
                set: { responses[prompt.id] = $0 }
            ))
            .font(.system(size: 15))
            .padding(Space.sm)
            .background(ColorsToken.Background.secondary)
            .clipShape(RoundedRectangle(cornerRadius: 10))
            
            HStack(spacing: Space.md) {
                Button {
                    responses[prompt.id] = ""
                    onClarificationSkip(prompt.id, prompt.question)
                } label: {
                    Text("Skip")
                        .font(.system(size: 14, weight: .medium))
                        .foregroundColor(ColorsToken.Text.secondary)
                }
                
                Spacer()
                
                Button {
                    let answer = responses[prompt.id]?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
                    guard !answer.isEmpty else { return }
                    responses[prompt.id] = ""
                    onClarificationSubmit(prompt.id, prompt.question, answer)
                } label: {
                    HStack(spacing: Space.xs) {
                        Text("Reply")
                        Image(systemName: "paperplane.fill")
                    }
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(.white)
                    .padding(.horizontal, Space.md)
                    .padding(.vertical, Space.sm)
                    .background(
                        (responses[prompt.id]?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ?? true)
                        ? ColorsToken.Text.secondary
                        : ColorsToken.Brand.primary
                    )
                    .clipShape(Capsule())
                }
                .disabled((responses[prompt.id]?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty) ?? true)
            }
        }
        .padding(Space.md)
        .background(ColorsToken.Surface.default)
        .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.medium, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: CornerRadiusToken.medium, style: .continuous)
                .stroke(ColorsToken.Brand.primary.opacity(0.3), lineWidth: 1)
        )
        .padding(.vertical, Space.sm)
    }
    
    // MARK: - Status Row
    private func statusRow(text: String) -> some View {
        HStack(spacing: Space.sm) {
            Circle()
                .fill(ColorsToken.Brand.primary.opacity(0.5))
                .frame(width: 6, height: 6)
            Text(text)
                .font(.system(size: 12))
                .foregroundColor(ColorsToken.Text.secondary)
        }
        .padding(.vertical, Space.xxs)
        .frame(maxWidth: .infinity, alignment: .center)
    }
    
    // MARK: - Error Row
    private func errorRow(text: String) -> some View {
        HStack(spacing: Space.sm) {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundColor(.red)
            Text(text)
                .font(.system(size: 13))
                .foregroundColor(.red)
        }
        .padding(Space.sm)
        .background(Color.red.opacity(0.1))
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .padding(.vertical, Space.xs)
    }
    
    // MARK: - Card View
    @ViewBuilder
    private func cardView(for card: CanvasCardModel) -> some View {
        switch card.data {
        case .sessionPlan:
            SessionPlanCard(model: card)
        case .inlineInfo(let text):
            CardContainer(status: card.status) {
                VStack(alignment: .leading, spacing: Space.xs) {
                    CardHeader(title: card.title ?? "Info", subtitle: card.subtitle, lane: card.lane, status: card.status, timestamp: card.publishedAt)
                    MyonText(text, style: .body)
                }
            }
        default:
            CardContainer(status: card.status) {
                VStack(alignment: .leading, spacing: Space.xs) {
                    CardHeader(title: card.title ?? "Update", subtitle: card.subtitle, lane: card.lane, status: card.status, timestamp: card.publishedAt)
                    if let detail = detailText(for: card) {
                        MyonText(detail, style: .body, color: ColorsToken.Text.secondary)
                    } else {
                        MyonText("New information available.", style: .body, color: ColorsToken.Text.secondary)
                    }
                }
            }
        }
    }
    
    private func detailText(for card: CanvasCardModel) -> String? {
        switch card.data {
        case .text(let text): return text
        case .inlineInfo(let text): return text
        case .suggestion(let title, let rationale): return rationale ?? title
        case .agentMessage(let message): return message.message
        default: return nil
        }
    }
    
    // MARK: - Timeline Items Builder
    private var timelineItems: [TimelineItem] {
        var items: [TimelineItem] = []
        
        // Process events
        let sortedEvents = renderedEvents
        for entry in sortedEvents {
            guard let kind = mapEventToKind(entry) else { continue }
            items.append(TimelineItem(
                id: "event-\(entry.id)",
                timestamp: entry.createdAt ?? Date.distantPast,
                kind: kind
            ))
        }
        
        // Process cards as artifacts
        for card in embeddedCards {
            items.append(TimelineItem(
                id: "card-\(card.id)",
                timestamp: card.publishedAt ?? Date(),
                kind: .artifact(card)
            ))
        }
        
        // Sort by timestamp
        return items.sorted { $0.timestamp < $1.timestamp }
    }
    
    private func mapEventToKind(_ entry: WorkspaceEvent) -> TimelineItemKind? {
        switch entry.event.eventType {
        case .userPrompt, .userResponse:
            let text = entry.event.content?["text"]?.value as? String ?? ""
            return .userMessage(text: text)
            
        case .thinking, .thought:
            // Build a ThoughtTrack from this summarized event
            let text = entry.event.content?["text"]?.value as? String ?? ""
            let duration = entry.event.content?["duration_s"]?.value as? Double ?? 0
            let tools = entry.event.content?["tools"]?.value as? [String] ?? []
            let isInProgress = entry.event.content?["is_in_progress"]?.value as? Bool ?? (entry.event.eventType == .thinking)
            
            var steps: [ThoughtStep] = []
            let timestamp = entry.createdAt ?? Date()
            
            // Add thinking step if duration > 0
            if duration > 0.5 {
                steps.append(ThoughtStep(
                    id: "\(entry.id)-thought",
                    kind: .insight,
                    text: String(format: "Thought for %.1fs", duration),
                    detail: nil,
                    duration: duration,
                    isComplete: !isInProgress,
                    timestamp: timestamp
                ))
            }
            
            // Add tool steps
            for tool in tools {
                steps.append(ThoughtStep(
                    id: "\(entry.id)-\(tool)",
                    kind: .tool,
                    text: humanReadableToolName(tool),
                    detail: nil,
                    duration: nil,
                    isComplete: !isInProgress,
                    timestamp: timestamp
                ))
            }
            
            if steps.isEmpty {
                // Fallback for simple thinking events
                steps.append(ThoughtStep(
                    id: entry.id,
                    kind: .thinking,
                    text: isInProgress ? "Working..." : text,
                    detail: nil,
                    duration: isInProgress ? nil : duration,
                    isComplete: !isInProgress,
                    timestamp: timestamp
                ))
            }
            
            if isInProgress {
                return .liveThoughtTrack(steps)
            } else {
                let track = ThoughtTrack(
                    id: entry.id,
                    steps: steps,
                    isComplete: true,
                    summary: nil,
                    totalDuration: duration
                )
                return .thoughtTrack(track)
            }
            
        case .agentResponse, .message:
            let text = entry.event.content?["text"]?.value as? String ?? ""
            guard !text.isEmpty else { return nil }
            return .agentResponse(text: text)
            
        case .clarificationRequest:
            guard let id = entry.event.content?["id"]?.value as? String,
                  let question = entry.event.content?["question"]?.value as? String else { return nil }
            return .clarification(TimelineClarificationPrompt(id: id, question: question))
            
        case .status:
            let text = entry.event.content?["text"]?.value as? String ?? entry.event.displayText
            return .status(text: text)
            
        case .error:
            let text = entry.event.content?["text"]?.value as? String ?? entry.event.displayText
            return .error(text: text)
            
        default:
            return nil
        }
    }
    
    private var renderedEvents: [WorkspaceEvent] {
        var result: [WorkspaceEvent] = []
        var pendingThinking: WorkspaceEvent?
        var toolsInFlight: [(name: String, start: Double)] = []
        var completedTools: [String] = []
        var thinkingDuration: Double = 0
        var lastThinkingStart: Double?
        
        let sortedEntries = events.sorted(by: { ($0.createdAt ?? .distantPast) < ($1.createdAt ?? .distantPast) })
        
        for entry in sortedEntries {
            let eventType = entry.event.eventType
            
            // Skip heartbeats and status events in rendering
            if eventType == .heartbeat || eventType == .status {
                continue
            }
            
            // Track thinking duration
            if eventType == .thinking {
                if lastThinkingStart == nil {
                    lastThinkingStart = entry.event.timestamp ?? entry.createdAt?.timeIntervalSince1970
                }
                pendingThinking = entry
                continue
            }
            
            // Thought closes a thinking block - accumulate duration
            if eventType == .thought {
                if let start = lastThinkingStart {
                    let end = entry.event.timestamp ?? entry.createdAt?.timeIntervalSince1970 ?? start
                    thinkingDuration += (end - start)
                }
                lastThinkingStart = nil
                pendingThinking = nil
                continue
            }
            
            // Tool running - track it
            if eventType == .toolRunning {
                let toolName = entry.event.content?["tool"]?.value as? String ?? "tool"
                let startTime = entry.event.timestamp ?? entry.createdAt?.timeIntervalSince1970 ?? 0
                // Only track if not already in flight
                if !toolsInFlight.contains(where: { $0.name == toolName }) {
                    toolsInFlight.append((name: toolName, start: startTime))
                }
                continue
            }
            
            // Tool complete - move to completed
            if eventType == .toolComplete {
                let toolName = entry.event.content?["tool"]?.value as? String ?? "tool"
                toolsInFlight.removeAll { $0.name == toolName }
                if !completedTools.contains(toolName) {
                    completedTools.append(toolName)
                }
                continue
            }
            
            // For user messages, agent responses, clarifications - flush pending thinking summary first
            if eventType == .userPrompt || eventType == .userResponse || 
               eventType == .agentResponse || eventType == .message ||
               eventType == .clarificationRequest {
                
                // Create a condensed thinking summary if we have data
                if thinkingDuration > 0 || !completedTools.isEmpty {
                    let summaryEvent = createThinkingSummary(
                        duration: thinkingDuration,
                        tools: completedTools,
                        timestamp: entry.createdAt
                    )
                    result.append(summaryEvent)
                    thinkingDuration = 0
                    completedTools = []
                    toolsInFlight = []
                }
                
                // Deduplicate consecutive identical text
                if let last = result.last,
                   normalizedText(for: entry) == normalizedText(for: last),
                   last.event.agent == entry.event.agent {
                    continue
                }
                
                result.append(entry)
            }
        }
        
        // Flush any remaining pending state at the end
        if thinkingDuration > 0 || !completedTools.isEmpty || !toolsInFlight.isEmpty {
            let allTools = completedTools + toolsInFlight.map { $0.name }
            let summaryEvent = createThinkingSummary(
                duration: thinkingDuration,
                tools: allTools,
                timestamp: sortedEntries.last?.createdAt,
                isInProgress: !toolsInFlight.isEmpty || pendingThinking != nil
            )
            result.append(summaryEvent)
        }
        
        return result
    }
    
    private func createThinkingSummary(duration: Double, tools: [String], timestamp: Date?, isInProgress: Bool = false) -> WorkspaceEvent {
        var parts: [String] = []
        
        if duration > 0.5 {
            parts.append(String(format: "Thought for %.1fs", duration))
        }
        
        let humanReadableTools = tools.map { humanReadableToolName($0) }
        if !humanReadableTools.isEmpty {
            parts.append(contentsOf: humanReadableTools)
        }
        
        let text = parts.isEmpty ? (isInProgress ? "Working..." : "Done") : parts.joined(separator: " • ")
        
        let content: [String: AnyCodable] = [
            "text": AnyCodable(text),
            "duration_s": AnyCodable(duration),
            "tools": AnyCodable(tools),
            "is_in_progress": AnyCodable(isInProgress)
        ]
        
        let streamEvent = StreamEvent(
            type: isInProgress ? "thinking" : "thought",
            agent: "orchestrator",
            content: content,
            timestamp: timestamp?.timeIntervalSince1970,
            metadata: nil
        )
        
        return WorkspaceEvent(id: UUID().uuidString, event: streamEvent, createdAt: timestamp)
    }
    
    private func normalizedText(for entry: WorkspaceEvent) -> String? {
        if let text = entry.event.content?["text"]?.value as? String {
            return text.trimmingCharacters(in: .whitespacesAndNewlines)
        }
        return entry.event.displayText.trimmingCharacters(in: .whitespacesAndNewlines)
    }
    
    private func synthesizeThought(thinking: WorkspaceEvent, thought: WorkspaceEvent) -> WorkspaceEvent {
        let start = (thinking.event.metadata?["start_time"]?.value as? Double)
            ?? (thought.event.metadata?["start_time"]?.value as? Double)
            ?? (thinking.event.timestamp ?? Date().timeIntervalSince1970)
        let end = thought.event.timestamp ?? Date().timeIntervalSince1970
        let duration = max(end - start, 0)
        let streamEvent = StreamEvent(
            type: "thought",
            agent: thought.event.agent,
            content: [
                "text": AnyCodable(String(format: "Thought for %.1fs", duration)),
                "duration_s": AnyCodable(duration)
            ],
            timestamp: thought.event.timestamp,
            metadata: thought.event.metadata
        )
        return WorkspaceEvent(id: UUID().uuidString, event: streamEvent, createdAt: thought.createdAt)
    }
    
    private func humanReadableToolName(_ name: String) -> String {
        switch name {
        case "tool_set_canvas_context": return "Setting context"
        case "tool_fetch_profile": return "Reviewing your profile"
        case "tool_fetch_recent_sessions": return "Checking recent workouts"
        case "tool_emit_agent_event": return "Logging"
        case "tool_request_clarification": return "Asking question"
        case "tool_format_workout_plan_cards": return "Formatting plan"
        case "tool_format_analysis_cards": return "Formatting analysis"
        case "tool_publish_cards": return "Publishing"
        case "get_user_workouts": return "Loading workout history"
        case "get_user_routines": return "Loading routines"
        case "list_exercises", "search_exercises": return "Searching exercises"
        case "get_user_templates": return "Loading templates"
        case "get_active_workout": return "Checking active workout"
        default: return name.replacingOccurrences(of: "_", with: " ").capitalized
        }
    }
    
    private static let timeFormatter: DateFormatter = {
        let f = DateFormatter()
        f.timeStyle = .short
        return f
    }()
}

// MARK: - Bubble Shape
private struct BubbleShape: Shape {
    let isUser: Bool
    
    func path(in rect: CGRect) -> Path {
        let radius: CGFloat = 18
        var path = Path()
        
        if isUser {
            // User bubble - rounded with slight tail on right
            path.addRoundedRect(in: rect, cornerSize: CGSize(width: radius, height: radius))
        } else {
            // Agent bubble - rounded with slight tail on left
            path.addRoundedRect(in: rect, cornerSize: CGSize(width: radius, height: radius))
        }
        
        return path
    }
}

// MARK: - Preview
#if DEBUG
struct WorkspaceTimelineView_Previews: PreviewProvider {
    static var previews: some View {
        WorkspaceTimelineView(
            events: [],
            embeddedCards: [],
            syntheticClarification: TimelineClarificationPrompt(id: "test", question: "What muscle groups do you want to focus on?"),
            answeredClarifications: [],
            onClarificationSubmit: { _, _, _ in },
            onClarificationSkip: { _, _ in }
        )
        .previewLayout(.sizeThatFits)
    }
}
#endif
