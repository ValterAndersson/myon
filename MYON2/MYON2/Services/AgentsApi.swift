import Foundation

struct AgentInvokeRequest: Codable {
    let userId: String
    let canvasId: String
    let message: String
}

enum AgentsApi {
    static func invokeCanvasOrchestrator(_ req: AgentInvokeRequest) async throws {
        struct Empty: Decodable {}
        let _: Empty = try await ApiClient.shared.postJSON("invokeCanvasOrchestrator", body: req)
    }
}


