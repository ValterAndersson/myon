import Foundation

protocol CanvasServiceProtocol {
    func applyAction(_ req: ApplyActionRequestDTO) async throws -> ApplyActionResponseDTO
    func bootstrapCanvas(for userId: String, purpose: String) async throws -> String
}

final class CanvasService: CanvasServiceProtocol {
    func applyAction(_ req: ApplyActionRequestDTO) async throws -> ApplyActionResponseDTO {
        return try await ApiClient.shared.postJSON("applyAction", body: req)
    }

    func bootstrapCanvas(for userId: String, purpose: String) async throws -> String {
        struct Req: Codable { let userId: String; let purpose: String }
        struct Res: Codable { let canvasId: String }
        struct Envelope<T: Codable>: Codable { let success: Bool; let data: T?; let error: Err? }
        struct Err: Codable { let code: String; let message: String }
        let env: Envelope<Res> = try await ApiClient.shared.postJSON("bootstrapCanvas", body: Req(userId: userId, purpose: purpose))
        if env.success, let data = env.data { return data.canvasId }
        throw NSError(domain: "CanvasService", code: 500, userInfo: [NSLocalizedDescriptionKey: env.error?.message ?? "Bootstrap failed"]) 
    }
}


