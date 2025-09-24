import Foundation

/// Temporary in-process backend replacement that generates a full canvas snapshot for demos.
enum MockCanvasBackend {
    static func generateCanvas(for userId: String, purpose: String) -> (canvasId: String, cards: [CanvasCardModel]) {
        let id = UUID().uuidString
        var cards: [CanvasCardModel] = []
        let steps: [AgentStreamStep] = [
            AgentStreamStep(kind: .thinking, durationMs: 800),
            AgentStreamStep(kind: .info, text: "Thought for 4 sec", durationMs: 1000),
            AgentStreamStep(kind: .info, text: "Let me understand your background and goals before coming up with a training program", durationMs: 1400),
            AgentStreamStep(kind: .lookup, text: "Looking up profile", durationMs: 900),
            AgentStreamStep(kind: .result, text: "Found profile", durationMs: 1000)
        ]
        let stream = CanvasCardModel(type: .analysis_task, lane: .analysis, title: "Planning Program", data: .agentStream(steps: steps), width: .full)
        cards.append(stream)
        return (id, cards)
    }
}


