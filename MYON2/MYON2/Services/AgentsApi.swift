import Foundation

struct AgentInvokeRequest: Codable {
    let userId: String
    let canvasId: String
    let message: String
    let correlationId: String
}

struct AgentResponseRequest: Codable {
    let canvasId: String
    let cardId: String?
    let response: [String: String]
}

enum AgentsApi {
    static func invokeCanvasOrchestrator(_ req: AgentInvokeRequest) async throws {
        struct Empty: Decodable {}
        DebugLogger.log(.agent, "invokeCanvasOrchestrator user=\(req.userId) canvas=\(req.canvasId)")
        let _: Empty = try await ApiClient.shared.postJSON("invokeCanvasOrchestrator", body: req)
    }
    
    static func respondToAgent(_ req: AgentResponseRequest) async throws {
        struct ResponseResult: Decodable {
            let success: Bool
            let response_id: String?
        }
        DebugLogger.log(.agent, "respondToAgent canvas=\(req.canvasId) card=\(req.cardId ?? "nil")")
        let result: ResponseResult = try await ApiClient.shared.postJSON("respondToAgent", body: req)
        DebugLogger.log(.agent, "respondToAgent result: \(result.success)")
    }
}


