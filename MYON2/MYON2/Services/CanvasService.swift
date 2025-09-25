import Foundation

protocol CanvasServiceProtocol {
    func applyAction(_ req: ApplyActionRequestDTO) async throws -> ApplyActionResponseDTO
    func bootstrapCanvas(for userId: String, purpose: String) async throws -> String
}

final class CanvasService: CanvasServiceProtocol {
    func applyAction(_ req: ApplyActionRequestDTO) async throws -> ApplyActionResponseDTO {
        DebugLogger.log(.canvas, "applyAction: v=\(req.expected_version ?? -1) type=\(req.action.type) card=\(req.action.card_id ?? "-")")
        let res: ApplyActionResponseDTO = try await ApiClient.shared.postJSON("applyAction", body: req)
        if DebugLogger.enabled {
            if let v = res.data?.version {
                DebugLogger.debug(.canvas, "applyAction result version=\(v) changed=\(res.data?.changed_cards?.count ?? 0)")
            }
            if let err = res.error { DebugLogger.error(.canvas, "applyAction error: \(err.code) - \(err.message)") }
        }
        return res
    }

    func bootstrapCanvas(for userId: String, purpose: String) async throws -> String {
        struct Req: Codable { let userId: String; let purpose: String }
        struct DataDTO: Codable { let canvasId: String }
        struct Envelope: Codable { let success: Bool; let data: DataDTO?; let error: ActionErrorDTO? }
        DebugLogger.log(.canvas, "bootstrapCanvas: user=\(userId) purpose=\(purpose)")
        let env: Envelope = try await ApiClient.shared.postJSON("bootstrapCanvas", body: Req(userId: userId, purpose: purpose))
        if DebugLogger.enabled {
            DebugLogger.debug(.canvas, "bootstrapCanvas success=\(env.success) id=\(env.data?.canvasId ?? "-")")
        }
        if env.success, let id = env.data?.canvasId { return id }
        let message = env.error?.message ?? "Failed to bootstrap canvas"
        throw NSError(domain: "CanvasService", code: 500, userInfo: [NSLocalizedDescriptionKey: message])
    }
}


