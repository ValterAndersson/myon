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
        let res: Res = try await ApiClient.shared.postJSON("bootstrapCanvas", body: Req(userId: userId, purpose: purpose))
        return res.canvasId
    }
}


