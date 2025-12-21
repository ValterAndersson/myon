import Foundation

struct InitializeSessionResponse: Codable {
    let success: Bool
    let sessionId: String?
    let isReused: Bool?
    let latencyMs: Int?
    let error: String?
}

/// Combined response from openCanvas - returns both canvasId and sessionId in one call
struct OpenCanvasResponse: Codable {
    let success: Bool
    let canvasId: String?
    let sessionId: String?
    let isNewSession: Bool?
    let resumeState: ResumeState?
    let timing: TimingInfo?
    let error: String?
    
    struct ResumeState: Codable {
        let cards: [AnyCodable]?
        let lastEntryCursor: String?
        let cardCount: Int?
    }
    
    struct TimingInfo: Codable {
        let totalMs: Int?
    }
}

/// Response from preWarmSession - warms the session before canvas is opened
struct PreWarmResponse: Codable {
    let success: Bool
    let sessionId: String?
    let isNew: Bool?
    let error: String?
}

protocol CanvasServiceProtocol {
    func applyAction(_ req: ApplyActionRequestDTO) async throws -> ApplyActionResponseDTO
    func bootstrapCanvas(for userId: String, purpose: String) async throws -> String
    func purgeCanvas(userId: String, canvasId: String, dropEvents: Bool, dropState: Bool, dropWorkspace: Bool) async throws
    func initializeSession(canvasId: String, purpose: String, forceNew: Bool) async throws -> String
    
    /// New combined endpoint - creates canvas and session in a single call
    func openCanvas(userId: String, purpose: String) async throws -> (canvasId: String, sessionId: String)
    
    /// Pre-warm the session before the canvas is opened (call on app launch or Home screen)
    func preWarmSession(userId: String, purpose: String) async throws -> String
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
    
    // MARK: - Optimized Endpoints
    
    /// Combined endpoint that creates canvas + session in ONE call (saves 1-2 network round trips)
    func openCanvas(userId: String, purpose: String) async throws -> (canvasId: String, sessionId: String) {
        struct Req: Codable { let userId: String; let purpose: String }
        
        DebugLogger.log(.canvas, "⏱️ openCanvas: user=\(userId) purpose=\(purpose)")
        let startTime = Date()
        
        let response: OpenCanvasResponse = try await ApiClient.shared.postJSON("openCanvas", body: Req(userId: userId, purpose: purpose))
        
        let elapsed = Date().timeIntervalSince(startTime)
        if DebugLogger.enabled {
            DebugLogger.debug(.canvas, "⏱️ openCanvas completed in \(Int(elapsed * 1000))ms - success=\(response.success) canvas=\(response.canvasId ?? "-") session=\(response.sessionId ?? "-") newSession=\(response.isNewSession ?? true)")
        }
        
        if response.success, let canvasId = response.canvasId, let sessionId = response.sessionId {
            return (canvasId, sessionId)
        }
        
        let message = response.error ?? "Failed to open canvas"
        throw NSError(domain: "CanvasService", code: 500, userInfo: [NSLocalizedDescriptionKey: message])
    }
    
    /// Pre-warm the session before the canvas is opened (call on app launch or when user navigates to Home)
    /// This reduces latency when the user actually opens the canvas
    func preWarmSession(userId: String, purpose: String) async throws -> String {
        struct Req: Codable { let userId: String; let purpose: String }
        
        DebugLogger.log(.canvas, "⏱️ preWarmSession: user=\(userId) purpose=\(purpose)")
        let startTime = Date()
        
        let response: PreWarmResponse = try await ApiClient.shared.postJSON("preWarmSession", body: Req(userId: userId, purpose: purpose))
        
        let elapsed = Date().timeIntervalSince(startTime)
        if DebugLogger.enabled {
            DebugLogger.debug(.canvas, "⏱️ preWarmSession completed in \(Int(elapsed * 1000))ms - success=\(response.success) session=\(response.sessionId ?? "-") isNew=\(response.isNew ?? true)")
        }
        
        if response.success, let sessionId = response.sessionId {
            return sessionId
        }
        
        let message = response.error ?? "Failed to pre-warm session"
        throw NSError(domain: "CanvasService", code: 500, userInfo: [NSLocalizedDescriptionKey: message])
    }
}
