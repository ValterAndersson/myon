import Foundation

struct AgentInvokeRequest: Codable {
    let userId: String
    let canvasId: String
    let message: String
    let correlationId: String
}

enum AgentsApi {
    static func invokeCanvasOrchestrator(_ req: AgentInvokeRequest) async throws {
        struct Empty: Decodable {}
        DebugLogger.log(.agent, "invokeCanvasOrchestrator user=\(req.userId) canvas=\(req.canvasId)")
        let _: Empty = try await ApiClient.shared.postJSON("invokeCanvasOrchestrator", body: req)
    }
}


