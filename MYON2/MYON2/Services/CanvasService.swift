import Foundation

struct InitializeSessionResponse: Codable {
    let success: Bool
    let sessionId: String?
    let isReused: Bool?
    let latencyMs: Int?
    let error: String?
}

protocol CanvasServiceProtocol {
    func applyAction(_ req: ApplyActionRequestDTO) async throws -> ApplyActionResponseDTO
    func bootstrapCanvas(for userId: String, purpose: String) async throws -> String
    func purgeCanvas(userId: String, canvasId: String, dropEvents: Bool, dropState: Bool, dropWorkspace: Bool) async throws
    func initializeSession(canvasId: String, purpose: String, forceNew: Bool) async throws -> String
}

extension CanvasServiceProtocol {
    func initializeSession(canvasId: String, purpose: String) async throws -> String {
        try await initializeSession(canvasId: canvasId, purpose: purpose, forceNew: false)
    }
}

extension CanvasServiceProtocol {
    func purgeCanvas(userId: String, canvasId: String) async throws {
        try await purgeCanvas(userId: userId, canvasId: canvasId, dropEvents: false, dropState: false, dropWorkspace: true)
    }
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

    func purgeCanvas(userId: String, canvasId: String, dropEvents: Bool = false, dropState: Bool = false, dropWorkspace: Bool = true) async throws {
        struct Req: Codable {
            let userId: String
            let canvasId: String
            let dropEvents: Bool
            let dropState: Bool
            let dropWorkspace: Bool
        }
        struct Envelope: Codable { let success: Bool; let error: ActionErrorDTO? }

        let req = Req(userId: userId, canvasId: canvasId, dropEvents: dropEvents, dropState: dropState, dropWorkspace: dropWorkspace)
        DebugLogger.log(.canvas, "purgeCanvas: user=\(userId) canvas=\(canvasId) dropEvents=\(dropEvents) dropState=\(dropState) dropWorkspace=\(dropWorkspace)")
        let env: Envelope = try await ApiClient.shared.postJSON("purgeCanvas", body: req)
        if DebugLogger.enabled {
            if env.success {
                DebugLogger.debug(.canvas, "purgeCanvas success")
            } else if let err = env.error {
                DebugLogger.error(.canvas, "purgeCanvas error: \(err.code) - \(err.message)")
            }
        }
        guard env.success else {
            let message = env.error?.message ?? "Failed to purge canvas"
            throw NSError(domain: "CanvasService", code: 500, userInfo: [NSLocalizedDescriptionKey: message])
        }
    }
    
    func initializeSession(canvasId: String, purpose: String, forceNew: Bool = false) async throws -> String {
        struct Req: Codable { let canvasId: String; let purpose: String; let forceNew: Bool }
        
        DebugLogger.log(.canvas, "initializeSession: canvas=\(canvasId) purpose=\(purpose) forceNew=\(forceNew)")
        let response: InitializeSessionResponse = try await ApiClient.shared.postJSON("initializeSession", body: Req(canvasId: canvasId, purpose: purpose, forceNew: forceNew))
        
        if DebugLogger.enabled {
            DebugLogger.debug(.canvas, "initializeSession success=\(response.success) sessionId=\(response.sessionId ?? "-") reused=\(response.isReused ?? false) latency=\(response.latencyMs ?? 0)ms")
        }
        
        if response.success, let sessionId = response.sessionId {
            return sessionId
        }
        
        let message = response.error ?? "Failed to initialize session"
        throw NSError(domain: "CanvasService", code: 500, userInfo: [NSLocalizedDescriptionKey: message])
    }
}
