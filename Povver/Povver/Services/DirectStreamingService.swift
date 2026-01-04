import Foundation
import Combine

// =============================================================================
// MARK: - DirectStreamingService.swift
// =============================================================================
//
// PURPOSE:
// SSE (Server-Sent Events) streaming client for real-time agent communication.
// Streams messages to the Agent Engine and receives streaming responses with
// tool calls, thinking steps, and text output.
//
// ARCHITECTURE CONTEXT:
// ┌─────────────────┐       ┌─────────────────────────────┐       ┌────────────────────┐
// │ iOS App         │       │ Firebase Functions          │       │ Agent Engine       │
// │                 │       │                             │       │ (Vertex AI)        │
// │ DirectStreaming │──SSE─►│ streamAgentNormalized       │──────►│ CanvasOrchestrator │
// │ Service         │◄─────│ (stream-agent-normalized.js)│◄──────│ (orchestrator.py)  │
// └─────────────────┘       └─────────────────────────────┘       └────────────────────┘
//
// KEY ENDPOINTS CALLED:
// - streamAgentNormalized → firebase_functions/functions/strengthos/stream-agent-normalized.js
//   SSE endpoint that normalizes Agent Engine events into structured stream
//
// - getServiceToken → firebase_functions/functions/auth/get-service-token.js
//   Exchanges Firebase ID token for GCP service account access token
//
// DIRECT AGENT ENGINE ENDPOINTS (fallback, not currently used):
// - https://{location}-aiplatform.googleapis.com/v1beta1/.../reasoningEngines/{id}:streamQuery
//   Direct Vertex AI Agent Engine streaming endpoint
// - :query endpoints for session management (create_session, list_sessions, etc.)
//
// STREAM EVENT FLOW:
// 1. User sends message → CanvasViewModel.sendMessage()
// 2. CanvasViewModel calls DirectStreamingService.streamQuery()
// 3. DirectStreamingService POSTs to streamAgentNormalized with SSE Accept header
// 4. Firebase Function proxies to Agent Engine and normalizes events
// 5. Agent Engine routes to Orchestrator → Coach/Planner/Copilot agents
// 6. Agent calls tools which emit _display metadata (see response_helpers.py)
// 7. Firebase extracts _display and emits structured SSE events
// 8. DirectStreamingService parses SSE → StreamEvent objects
// 9. UI renders StreamEvents in ThoughtTrackView and AgentStreamCard
//
// EVENT TYPES RECEIVED:
// - session: Contains sessionId for session continuity
// - text_delta: Partial text chunk from agent
// - text_commit: Final committed text
// - list_item: Formatted list item (bullet point)
// - tool_started: Agent is calling a tool (with name)
// - tool_result: Tool completed (with name and counts)
// - code_block: Code block open/close
// - error: Error from agent
//
// RELATED IOS FILES:
// - ChatService.swift: Manages chat sessions, uses this for streaming
// - CanvasViewModel.swift: Uses streamQuery for agent invocations
// - AgentProgressState.swift: Tracks tool execution phases
// - StreamEvent.swift (Models): Event data model
// - ThoughtTrackView.swift: Renders tool_started/tool_result events
// - AgentStreamCard.swift: Renders streaming text output
//
// RELATED AGENT FILES:
// - adk_agent/canvas_orchestrator/app/agents/orchestrator.py: Routes to agents
// - adk_agent/canvas_orchestrator/app/libs/tools_common/response_helpers.py: _display
//
// =============================================================================

// MARK: - Session Details
struct SessionDetails {
    let id: String
    let userId: String
    let state: [String: Any]
    let events: [[String: Any]]
    let lastUpdateTime: Double
}

/// Service for direct streaming communication with the Agent Engine API
class DirectStreamingService: ObservableObject {
    static let shared = DirectStreamingService()
    
    private let projectId = "myon-53d85"
    private let location = "us-central1"
    private let reasoningEngineId = "4683295011721183232"
    
    private var gcpAuthToken: String?
    private var tokenExpiryTime: Date?
    
    private let session = URLSession(configuration: .default)
    
    // MARK: - Public Methods
    
    /// Feature flag to toggle normalized SSE endpoint
    private var useNormalizedStream: Bool {
        #if DEBUG
        return true
        #else
        return true
        #endif
    }

    /// Query the agent with streaming response (Canvas version with AsyncSequence)
    func streamQuery(
        userId: String,
        canvasId: String,
        message: String,
        correlationId: String,
        sessionId: String?
    ) -> AsyncThrowingStream<StreamEvent, Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                let streamStartTime = Date()
                var eventCount = 0
                
                do {
                    // Start pipeline logging (new focused logger)
                    AgentPipelineLogger.startRequest(
                        correlationId: correlationId,
                        canvasId: canvasId,
                        sessionId: sessionId,
                        message: message
                    )
                    
                    // Get Firebase ID token
                    guard let currentUser = AuthService.shared.currentUser else {
                        AgentPipelineLogger.failRequest(error: "Not authenticated", afterMs: 0)
                        continuation.finish(throwing: StreamingError.notAuthenticated)
                        return
                    }
                    
                    let idToken = try await currentUser.getIDToken()
                    
                    // Use streamAgentNormalized endpoint
                    let url = URL(string: "https://us-central1-myon-53d85.cloudfunctions.net/streamAgentNormalized")!
                    var request = URLRequest(url: url)
                    request.httpMethod = "POST"
                    request.setValue("Bearer \(idToken)", forHTTPHeaderField: "Authorization")
                    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
                    request.setValue("text/event-stream", forHTTPHeaderField: "Accept")
                    
                    let body: [String: Any] = [
                        "userId": userId,
                        "canvasId": canvasId,
                        "message": message,
                        "correlationId": correlationId,
                        "sessionId": sessionId as Any
                    ].compactMapValues { $0 }
                    request.httpBody = try JSONSerialization.data(withJSONObject: body)
                    
                    // Stream the response
                    let (asyncBytes, response) = try await session.bytes(for: request)
                    
                    guard let httpResponse = response as? HTTPURLResponse else {
                        throw NSError(domain: "DirectStreamingService", code: -1,
                                    userInfo: [NSLocalizedDescriptionKey: "Invalid response type"])
                    }
                    
                    if httpResponse.statusCode != 200 {
                        AgentPipelineLogger.shared.pipelineStep(.error, "HTTP \(httpResponse.statusCode)")
                        throw NSError(domain: "DirectStreamingService", code: httpResponse.statusCode,
                                    userInfo: [NSLocalizedDescriptionKey: "HTTP \(httpResponse.statusCode)"])
                    }
                    
                    // Parse SSE stream
                    for try await line in asyncBytes.lines {
                        if line.hasPrefix("data: ") {
                            let jsonStr = String(line.dropFirst(6))
                            
                            if jsonStr == "[DONE]" {
                                let durationMs = Int(Date().timeIntervalSince(streamStartTime) * 1000)
                                AgentPipelineLogger.endRequest(totalMs: durationMs, toolCount: nil)
                                continuation.finish()
                                break
                            }
                            
                            if let data = jsonStr.data(using: .utf8),
                               let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                                
                                // Parse content with proper AnyCodable handling
                                var contentDict: [String: AnyCodable]? = nil
                                if let rawContent = json["content"] as? [String: Any] {
                                    contentDict = rawContent.mapValues { AnyCodable($0) }
                                }
                                
                                var metadataDict: [String: AnyCodable]? = nil
                                if let rawMeta = json["metadata"] as? [String: Any] {
                                    metadataDict = rawMeta.mapValues { AnyCodable($0) }
                                }
                                
                                // Parse the event
                                let event = StreamEvent(
                                    type: json["type"] as? String ?? "unknown",
                                    agent: json["agent"] as? String,
                                    content: contentDict,
                                    timestamp: json["timestamp"] as? Double,
                                    metadata: metadataDict
                                )
                                
                                eventCount += 1
                                
                                // Log with new focused pipeline logger
                                var contentForLog: [String: Any] = [:]
                                if let rawContent = json["content"] as? [String: Any] {
                                    contentForLog = rawContent
                                }
                                var metaForLog: [String: Any] = [:]
                                if let rawMeta = json["metadata"] as? [String: Any] {
                                    metaForLog = rawMeta
                                }
                                AgentPipelineLogger.event(
                                    type: event.type,
                                    content: contentForLog.isEmpty ? nil : contentForLog,
                                    agent: event.agent,
                                    metadata: metaForLog.isEmpty ? nil : metaForLog
                                )
                                
                                continuation.yield(event)
                            }
                        }
                    }
                    
                    let durationMs = Int(Date().timeIntervalSince(streamStartTime) * 1000)
                    AgentPipelineLogger.endRequest(totalMs: durationMs, toolCount: nil)
                    continuation.finish()
                    
                } catch {
                    let durationMs = Int(Date().timeIntervalSince(streamStartTime) * 1000)
                    AgentPipelineLogger.failRequest(error: error.localizedDescription, afterMs: durationMs)
                    continuation.finish(throwing: error)
                }
            }
            
            continuation.onTermination = { @Sendable _ in
                task.cancel()
            }
        }
    }
    
    /// Query the agent with streaming response (Legacy version)
    func streamQuery(
        message: String,
        userId: String,
        sessionId: String? = nil,
        progressHandler: @escaping (_ partialText: String?, _ action: String?) -> Void,
        completion: @escaping (Result<(response: String, sessionId: String?), Error>) -> Void
    ) {
        Task {
            do {
                // Ensure we have a valid auth token
                let token = try await getAuthToken()
                
                var asyncBytes: URLSession.AsyncBytes
                var response: URLResponse
                
                if useNormalizedStream {
                    // Use Firebase Function SSE normalizer
                    guard let sseURL = URL(string: "https://us-central1-myon-53d85.cloudfunctions.net/streamAgentNormalized") else {
                        throw StreamingError.invalidURL
                    }
                    var req = URLRequest(url: sseURL)
                    req.httpMethod = "POST"
                    // For server auth, use Firebase ID token, not GCP access token
                    guard let currentUser = AuthService.shared.currentUser else { throw StreamingError.notAuthenticated }
                    let idToken = try await currentUser.getIDToken()
                    req.setValue("Bearer \(idToken)", forHTTPHeaderField: "Authorization")
                    req.setValue("application/json", forHTTPHeaderField: "Content-Type")
                    req.setValue("text/event-stream", forHTTPHeaderField: "Accept")
                    let body: [String: Any] = [
                        "message": message,
                        "sessionId": sessionId as Any,
                        "markdown_policy": [
                            "bullets": "-",
                            "max_bullets": 6,
                            "no_headers": true
                        ]
                    ].compactMapValues { $0 }
                    req.httpBody = try JSONSerialization.data(withJSONObject: body)
                    (asyncBytes, response) = try await session.bytes(for: req)
                } else {
                    // Direct Vertex Agent Engine fallback
                    let url = URL(string: "https://\(location)-aiplatform.googleapis.com/v1beta1/projects/\(projectId)/locations/\(location)/reasoningEngines/\(reasoningEngineId):streamQuery")!
                    var request = URLRequest(url: url)
                    request.httpMethod = "POST"
                    request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
                    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
                    let payload: [String: Any] = [
                        "class_method": "stream_query",
                        "input": [
                            "user_id": userId,
                            "message": message,
                            "session_id": sessionId as Any
                        ].compactMapValues { $0 }
                    ]
                    request.httpBody = try JSONSerialization.data(withJSONObject: payload)
                    (asyncBytes, response) = try await session.bytes(for: request)
                }
                
                guard let httpResponse = response as? HTTPURLResponse,
                      httpResponse.statusCode == 200 else {
                    throw StreamingError.invalidResponse
                }
                
                var fullResponse = ""
                var pendingBuffer = ""
                var lastFlushedTail = ""
                var seenChunkFingerprints: Set<String> = []
                var seenActions: Set<String> = []
                var returnedSessionId: String?
                
                
                // Process streaming response
                for try await line in asyncBytes.lines {
                    if useNormalizedStream {
                        // Canonical SSE NDJSON events
                        guard let event = parseStreamingEvent(line) else { continue }
                        if let type = event["type"] as? String {
                            switch type {
                            case "session":
                                returnedSessionId = event["sessionId"] as? String
                            case "list_item":
                                if let text = event["text"] as? String, !text.isEmpty {
                                    let bullet = "- " + text + "\n"
                                    pendingBuffer += bullet
                                    let (commit, keep) = Self.segmentAndSanitizeMarkdown(pendingBuffer)
                                    if !commit.isEmpty {
                                        var addition = Self.ensureJoinSpacing(base: fullResponse, addition: commit)
                                        addition = Self.cleanLeadingFiller(addition)
                                        let commitToAppend = Self.dedupeTrailing(base: fullResponse, addition: addition, lastTail: lastFlushedTail)
                                        if !commitToAppend.isEmpty {
                                            let fp = Self.fingerprint(commitToAppend)
                                            if !seenChunkFingerprints.contains(fp) {
                                                fullResponse += commitToAppend
                                                lastFlushedTail = String(fullResponse.suffix(200))
                                                seenChunkFingerprints.insert(fp)
                                                progressHandler(fullResponse, nil)
                                            }
                                        }
                                    }
                                    pendingBuffer = keep
                                }
                            case "code_block":
                                // For now, ignore open/close; text comes via deltas. Later: render monospace blocks.
                                break
                            case "text_delta":
                                if let text = event["text"] as? String, !text.isEmpty {
                                    pendingBuffer += text
                                    let (commit, keep) = Self.segmentAndSanitizeMarkdown(pendingBuffer)
                                    if !commit.isEmpty {
                                        var addition = Self.ensureJoinSpacing(base: fullResponse, addition: commit)
                                        addition = Self.cleanLeadingFiller(addition)
                                        let commitToAppend = Self.dedupeTrailing(base: fullResponse, addition: addition, lastTail: lastFlushedTail)
                                        if !commitToAppend.isEmpty {
                                            let fp = Self.fingerprint(commitToAppend)
                                            if !seenChunkFingerprints.contains(fp) {
                                                fullResponse += commitToAppend
                                                lastFlushedTail = String(fullResponse.suffix(200))
                                                seenChunkFingerprints.insert(fp)
                                                progressHandler(fullResponse, nil)
                                            }
                                        }
                                    }
                                    pendingBuffer = keep
                                }
                            case "text_commit":
                                if let text = event["text"] as? String, !text.isEmpty {
                                    var addition = Self.ensureJoinSpacing(base: fullResponse, addition: text)
                                    addition = Self.cleanLeadingFiller(addition)
                                    // Drop overlap if commit contains the pending buffer prefix
                                    if !pendingBuffer.isEmpty && addition.hasPrefix(pendingBuffer) {
                                        addition = String(addition.dropFirst(pendingBuffer.count))
                                    }
                                    let commitToAppend = Self.dedupeTrailing(base: fullResponse, addition: addition, lastTail: lastFlushedTail)
                                    if !commitToAppend.isEmpty {
                                        fullResponse += commitToAppend
                                        lastFlushedTail = String(fullResponse.suffix(200))
                                        progressHandler(fullResponse, nil)
                                    }
                                    pendingBuffer = ""
                                }
                            case "tool_started":
                                if let name = event["name"] as? String {
                                    let human = getHumanReadableFunctionName(name)
                                    if !seenActions.contains(human) {
                                        seenActions.insert(human)
                                        progressHandler(nil, human)
                                    }
                                }
                            case "tool_result":
                                if let name = event["name"] as? String {
                                    let human = getHumanReadableFunctionResponseName(name)
                                    var detail = ""
                                    if let counts = event["counts"] as? [String: Any], let items = counts["items"] as? Int {
                                        detail = " - found \(items) item\(items == 1 ? "" : "s")"
                                    }
                                    let actionLine = human + detail
                                    if !seenActions.contains(actionLine) {
                                        seenActions.insert(actionLine)
                                        progressHandler(nil, actionLine)
                                    }
                                }
                            case "error":
                                // Optionally surface error
                                break
                            default:
                                break
                            }
                        }
                    } else {
                        // Fallback: raw Agent Engine stream
                        if let event = parseStreamingEvent(line) {
                            // Extract session ID if present
                            if let actions = event["actions"] as? [String: Any] {
                                if let sid = actions["session_id"] as? String {
                                    returnedSessionId = sid
                                }
                            }
                            
                            // Extract and handle content
                            if let content = event["content"] as? [String: Any],
                               let parts = content["parts"] as? [[String: Any]] {
                                for part in parts {
                                    // Handle regular text
                                    if let text = part["text"] as? String {
                                        if !text.isEmpty {
                                            // Append to pending buffer and flush only safe segments
                                            pendingBuffer += text
                                            let (commit, keep) = Self.segmentAndSanitizeMarkdown(pendingBuffer)
                                            if !commit.isEmpty {
                                                var addition = Self.ensureJoinSpacing(base: fullResponse, addition: commit)
                                                addition = Self.cleanLeadingFiller(addition)
                                                let commitToAppend = Self.dedupeTrailing(base: fullResponse, addition: addition, lastTail: lastFlushedTail)
                                                if !commitToAppend.isEmpty {
                                                    let fp = Self.fingerprint(commitToAppend)
                                                    if !seenChunkFingerprints.contains(fp) {
                                                        fullResponse += commitToAppend
                                                        lastFlushedTail = String(fullResponse.suffix(200))
                                                        seenChunkFingerprints.insert(fp)
                                                        progressHandler(fullResponse, nil)
                                                    }
                                                }
                                            }
                                            pendingBuffer = keep
                                        }
                                    }
                                    
                                    // Handle function calls
                                    if let functionCall = part["function_call"] as? [String: Any],
                                       let name = functionCall["name"] as? String {
                                        let args = functionCall["args"] as? [String: Any]
                                        let argsString = formatFunctionArgs(args)
                                        let humanReadableName = getHumanReadableFunctionName(name)
                                        let actionLine = "\(humanReadableName)\(argsString)"
                                        if !seenActions.contains(actionLine) {
                                            seenActions.insert(actionLine)
                                            progressHandler(nil, actionLine)
                                        }
                                    }
                                    
                                    // Handle function responses
                                    if let functionResponse = part["function_response"] as? [String: Any],
                                       let name = functionResponse["name"] as? String {
                                        let humanReadableName = getHumanReadableFunctionResponseName(name)
                                        var responseJson: [String: Any]? = nil
                                        if let responseDict = functionResponse["response"] as? [String: Any] {
                                            responseJson = responseDict
                                        } else if let response = functionResponse["response"] as? String,
                                                  let responseData = response.data(using: .utf8),
                                                  let parsed = try? JSONSerialization.jsonObject(with: responseData) as? [String: Any] {
                                            responseJson = parsed
                                        }
                                        if let responseJson = responseJson {
                                            var responseDetail = ""
                                            switch name {
                                            case "get_user_templates":
                                                if let data = responseJson["data"] as? [[String: Any]] { responseDetail = " - found \(data.count) template\(data.count == 1 ? "" : "s")" }
                                            case "get_user_workouts":
                                                if let data = responseJson["data"] as? [[String: Any]] { responseDetail = " - found \(data.count) workout\(data.count == 1 ? "" : "s")" }
                                            case "search_exercises", "list_exercises":
                                                if let data = responseJson["data"] as? [[String: Any]] { responseDetail = " - found \(data.count) exercise\(data.count == 1 ? "" : "s")" }
                                            case "get_user_routines":
                                                if let data = responseJson["data"] as? [[String: Any]] { responseDetail = " - found \(data.count) routine\(data.count == 1 ? "" : "s")" }
                                            default:
                                                break
                                            }
                                            let actionLine = "\(humanReadableName)\(responseDetail)"
                                            if !seenActions.contains(actionLine) {
                                                seenActions.insert(actionLine)
                                                progressHandler(nil, actionLine)
                                            }
                                        } else {
                                            if !seenActions.contains(humanReadableName) {
                                                seenActions.insert(humanReadableName)
                                                progressHandler(nil, humanReadableName)
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
                
                // Flush any remaining buffered text at stream end
                if !pendingBuffer.isEmpty {
                    let (commit, keep) = Self.segmentAndSanitizeMarkdown(pendingBuffer, allowPartial: true)
                    var finalAdd = Self.ensureJoinSpacing(base: fullResponse, addition: commit + keep)
                    finalAdd = Self.cleanLeadingFiller(finalAdd)
                    let commitToAppend = Self.dedupeTrailing(base: fullResponse, addition: finalAdd, lastTail: lastFlushedTail)
                    if !commitToAppend.isEmpty {
                        fullResponse += commitToAppend
                        progressHandler(fullResponse, nil)
                    }
                }
                completion(.success((fullResponse, returnedSessionId ?? sessionId)))
                
            } catch {
                completion(.failure(error))
            }
        }
    }
    
    /// Split incoming text into a commit-safe prefix and a kept suffix.
    /// Ensures we do not flush half list markers or half code fences, and normalizes bullets.
    private static func segmentAndSanitizeMarkdown(_ incoming: String, allowPartial: Bool = false) -> (commit: String, keep: String) {
        if incoming.isEmpty { return ("", "") }

        // Normalize unwanted bullets, headings, and stray characters early
        var text = incoming
            .replacingOccurrences(of: "\u{2022}", with: "-") // •
            .replacingOccurrences(of: "\u{2023}", with: "-") // ‣
            .replacingOccurrences(of: "\t* ", with: "- ")
            .replacingOccurrences(of: "\r", with: "")

        // Drop markdown headings to avoid giant section titles mid-stream
        let noHeadings = text
            .components(separatedBy: "\n")
            .filter { ln in
                let t = ln.trimmingCharacters(in: .whitespaces)
                return !(t.hasPrefix("# ") || t.hasPrefix("## ") || t.hasPrefix("### "))
            }
            .joined(separator: "\n")
        text = noHeadings

        // If we allow partial at stream end, just return normalized content
        if allowPartial { return (text, "") }

        // Heuristics: commit up to the last safe boundary
        // Safe boundaries: paragraph break, end of sentence, start of new list item
        let delimiters = ["\n\n", ". ", "! ", "? ", "\n- ", "\n* ", "\n1. "]
        var cutIndex: String.Index? = nil

        for delim in delimiters {
            if let range = text.range(of: delim, options: [.backwards]) {
                cutIndex = range.upperBound
                break
            }
        }

        // Avoid flushing when inside an open code fence (odd number of ```)
        let fenceCount = text.components(separatedBy: "```").count - 1
        let isFenceOpen = fenceCount % 2 == 1

        if let idx = cutIndex {
            let commit = String(text[..<idx])
            if isFenceOpen {
                // Keep everything if fence is open
                return ("", text)
            }
            let keep = String(text[idx...])
            return (commit, keep)
        }

        // If nothing safe found, be conservative: don't flush yet
        return ("", text)
    }

    // Fingerprint small chunks to drop exact duplicates without CryptoKit
    private static func fingerprint(_ s: String) -> String {
        let trimmed = s.trimmingCharacters(in: .whitespacesAndNewlines)
        let sample = String(trimmed.suffix(128)).lowercased()
        var hash: UInt64 = 5381
        for u in sample.unicodeScalars { hash = ((hash << 5) &+ hash) &+ UInt64(u.value) }
        return String(hash)
    }

    // Drop additions that already appear at the end of the base text
    private static func dedupeTrailing(base: String, addition: String, lastTail: String, minLen: Int = 6) -> String {
        let add = addition.trimmingCharacters(in: .whitespacesAndNewlines)
        if add.isEmpty { return "" }
        let tail = lastTail.isEmpty ? String(base.suffix(200)) : lastTail
        if !tail.isEmpty && (tail.hasSuffix(add) || tail.contains(add)) { return "" }
        // Also avoid re-adding if base already contains the addition near the end
        let window = String(base.suffix(800))
        if window.contains(add) && add.count >= minLen { return "" }
        return addition
    }

    // If base ends with a letter/number and addition starts with a letter (no leading space), insert a space
    private static func ensureJoinSpacing(base: String, addition: String) -> String {
        guard let last = base.unicodeScalars.last else { return addition }
        guard let first = addition.unicodeScalars.first else { return addition }
        let ws = CharacterSet.whitespacesAndNewlines
        let letters = CharacterSet.letters
        if !ws.contains(last) && letters.contains(first) {
            return " " + addition
        }
        return addition
    }

    // Remove filler phrases at the start of paragraphs
    private static func cleanLeadingFiller(_ text: String) -> String {
        let fillers = ["Okay, ", "Of course, ", "Sure, ", "Got it, ", "Alright, "]
        let lines = text.components(separatedBy: "\n").map { line -> String in
            var ln = line
            for f in fillers {
                if ln.hasPrefix(f) { ln = String(ln.dropFirst(f.count)) }
            }
            return ln
        }
        // Collapse double spaces created by removals
        return lines.joined(separator: "\n").replacingOccurrences(of: "  ", with: " ")
    }

    /// Create a new session
    func createSession(userId: String) async throws -> String {
        let token = try await getAuthToken()
        
        let url = URL(string: "https://\(location)-aiplatform.googleapis.com/v1beta1/projects/\(projectId)/locations/\(location)/reasoningEngines/\(reasoningEngineId):query")!
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        let payload: [String: Any] = [
            "class_method": "create_session",
            "input": [
                "user_id": userId,
                "state": [
                    "user:id": userId
                ]
            ]
        ]
        
        request.httpBody = try JSONSerialization.data(withJSONObject: payload)
        
        let (data, response) = try await session.data(for: request)
        
        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else {
            throw StreamingError.sessionCreationFailed
        }
        
        let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        guard let output = json?["output"] as? [String: Any],
              let sessionId = output["id"] as? String else {
            throw StreamingError.invalidSessionResponse
        }
        
        return sessionId
    }
    
    /// List sessions for a user
    func listSessions(userId: String) async throws -> [String] {
        let token = try await getAuthToken()
        
        let url = URL(string: "https://\(location)-aiplatform.googleapis.com/v1beta1/projects/\(projectId)/locations/\(location)/reasoningEngines/\(reasoningEngineId):query")!
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        let payload: [String: Any] = [
            "class_method": "list_sessions",
            "input": [
                "user_id": userId
            ]
        ]
        
        request.httpBody = try JSONSerialization.data(withJSONObject: payload)
        
        let (data, response) = try await session.data(for: request)
        
        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else {
            throw StreamingError.listSessionsFailed
        }
        
        let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        
        // ADK response examples:
        // 1. { "output": [ { "id": "123" }, ... ] }
        // 2. { "output": { "sessions": [ { "id": "123" }, ... ] } }
        
        var sessionArray: [[String: Any]] = []
        
        if let arr = json?["output"] as? [[String: Any]] {
            sessionArray = arr
        } else if let dict = json?["output"] as? [String: Any],
                  let arr = dict["sessions"] as? [[String: Any]] {
            sessionArray = arr
        } else {
            if let json = json {
                print("Unexpected list_sessions response format: \(json)")
            }
            return []
        }
        
        // Extract IDs
        return sessionArray.compactMap { sessionObj in
            if let sid = sessionObj["id"] as? String {
                return sid
            }
            return sessionObj["session_id"] as? String
        }
    }
    
    /// Delete a session
    func deleteSession(sessionId: String, userId: String) async throws {
        let token = try await getAuthToken()
        
        let url = URL(string: "https://\(location)-aiplatform.googleapis.com/v1beta1/projects/\(projectId)/locations/\(location)/reasoningEngines/\(reasoningEngineId):query")!
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        let payload: [String: Any] = [
            "class_method": "delete_session",
            "input": [
                "user_id": userId,
                "session_id": sessionId
            ]
        ]
        
        request.httpBody = try JSONSerialization.data(withJSONObject: payload)
        
        let (_, response) = try await session.data(for: request)
        
        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else {
            throw StreamingError.deleteSessionFailed
        }
    }
    
    /// Get session details including conversation history
    func getSession(sessionId: String, userId: String) async throws -> SessionDetails {
        // Ensure we have a valid auth token
        let token = try await getAuthToken()
        
        // Use the :query endpoint with class_method
        let url = URL(string: "https://\(location)-aiplatform.googleapis.com/v1beta1/projects/\(projectId)/locations/\(location)/reasoningEngines/\(reasoningEngineId):query")!
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        let payload: [String: Any] = [
            "class_method": "get_session",
            "input": [
                "user_id": userId,
                "session_id": sessionId
            ]
        ]
        
        request.httpBody = try JSONSerialization.data(withJSONObject: payload)
        
        let (data, response) = try await URLSession.shared.data(for: request)
        
        guard let httpResponse = response as? HTTPURLResponse else {
            throw StreamingError.invalidResponse
        }
        
        guard httpResponse.statusCode == 200 else {
            throw StreamingError.httpError(statusCode: httpResponse.statusCode)
        }
        
        // Parse the session details from the output
        let json = try JSONSerialization.jsonObject(with: data) as? [String: Any] ?? [:]
        let output = json["output"] as? [String: Any] ?? [:]
        
        return SessionDetails(
            id: output["id"] as? String ?? sessionId,
            userId: output["user_id"] as? String ?? userId,
            state: output["state"] as? [String: Any] ?? [:],
            events: output["events"] as? [[String: Any]] ?? [],
            lastUpdateTime: output["last_update_time"] as? Double ?? Date().timeIntervalSince1970
        )
    }
    
    // MARK: - Private Methods
    
    private func getAuthToken() async throws -> String {
        // Check if we have a valid cached token
        if let token = gcpAuthToken,
           let expiry = tokenExpiryTime,
           expiry > Date() {
            return token
        }
        
        // Get new token using Firebase Auth
        guard let user = AuthService.shared.currentUser else {
            throw StreamingError.notAuthenticated
        }
        
        print("User authenticated: \(user.uid)")
        
        // Get Firebase ID token
        do {
            print("Getting Firebase ID token...")
            let idToken = try await user.getIDToken()
            
            // Call HTTP endpoint with auth token
            let url = URL(string: "https://us-central1-myon-53d85.cloudfunctions.net/getServiceToken")!
            var request = URLRequest(url: url)
            request.httpMethod = "POST"
            request.setValue("Bearer \(idToken)", forHTTPHeaderField: "Authorization")
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            
            print("Getting service account access token...")
            let (data, response) = try await session.data(for: request)
            
            guard let httpResponse = response as? HTTPURLResponse,
                  httpResponse.statusCode == 200 else {
                print("HTTP error: \((response as? HTTPURLResponse)?.statusCode ?? -1)")
                if let responseData = String(data: data, encoding: .utf8) {
                    print("Response: \(responseData)")
                }
                throw StreamingError.tokenExchangeFailed
            }
            
            print("Exchange token response received")
            let resultData = try JSONSerialization.jsonObject(with: data) as? [String: Any]
            
            guard let resultData = resultData,
                  let accessToken = resultData["accessToken"] as? String else {
                print("Failed to extract accessToken from response")
                print("Result was: \(String(data: data, encoding: .utf8) ?? "nil")")
                throw StreamingError.invalidTokenResponse
            }
            
            // Extract expiry time if available
            if let expiryTimestamp = resultData["expiryDate"] as? TimeInterval {
                self.tokenExpiryTime = Date(timeIntervalSince1970: expiryTimestamp / 1000)
            } else {
                // Default to 1 hour if no expiry provided
                self.tokenExpiryTime = Date().addingTimeInterval(3600)
            }
            
            self.gcpAuthToken = accessToken
            print("Successfully obtained GCP access token")
            return accessToken
        } catch let error as NSError {
            print("Error: \(error.localizedDescription)")
            print("Error code: \(error.code)")
            print("Error domain: \(error.domain)")
            throw StreamingError.tokenExchangeFailed
        } catch {
            print("Unknown error: \(error)")
            throw StreamingError.tokenExchangeFailed
        }
    }
    
    private func parseStreamingEvent(_ line: String) -> [String: Any]? {
        // Remove "data: " prefix if present
        let jsonString = line.hasPrefix("data: ") ? String(line.dropFirst(6)) : line
        
        guard !jsonString.isEmpty,
              let data = jsonString.data(using: .utf8),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return nil
        }
        
        return json
    }
    
    /// Format function arguments for display
    private func formatFunctionArgs(_ args: [String: Any]?) -> String {
        guard let args = args, !args.isEmpty else { return "" }
        
        // Extract key arguments for display
        var displayParts: [String] = []
        
        // Common argument patterns - avoid showing user_id
        if let startDate = args["start_date"] as? String {
            displayParts.append("from \(formatDate(startDate))")
        }
        if let endDate = args["end_date"] as? String {
            displayParts.append("to \(formatDate(endDate))")
        }
        if let limit = args["limit"] {
            displayParts.append("limit: \(limit)")
        }
        if let muscleGroups = args["muscle_groups"] as? String {
            displayParts.append("for \(muscleGroups)")
        }
        if let equipment = args["equipment"] as? String {
            displayParts.append("using \(equipment)")
        }
        if let query = args["query"] as? String {
            displayParts.append("\"\(query)\"")
        }
        if args["template_id"] != nil {
            displayParts.append("template")
        }
        if args["workout_id"] != nil {
            displayParts.append("workout")
        }
        if args["routine_id"] != nil {
            displayParts.append("routine")
        }
        
        // If we have display parts, format them nicely
        if !displayParts.isEmpty {
            return " \(displayParts.joined(separator: ", "))"
        }
        
        // Otherwise, return empty string (no args display)
        return ""
    }
    
    /// Format ISO date string for display
    private func formatDate(_ isoString: String) -> String {
        // Parse ISO date string
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        
        if let date = formatter.date(from: isoString) {
            let displayFormatter = DateFormatter()
            displayFormatter.dateStyle = .short
            displayFormatter.timeStyle = .none
            return displayFormatter.string(from: date)
        }
        
        // Fallback: try without fractional seconds
        formatter.formatOptions = [.withInternetDateTime]
        if let date = formatter.date(from: isoString) {
            let displayFormatter = DateFormatter()
            displayFormatter.dateStyle = .short
            displayFormatter.timeStyle = .none
            return displayFormatter.string(from: date)
        }
        
        // If parsing fails, return a shortened version
        return String(isoString.prefix(10))
    }
    
    private func getHumanReadableFunctionName(_ name: String) -> String {
        switch name {
        // User management
        case "get_user": return "Loading user profile"
        case "get_user_preferences": return "Loading preferences"
        case "update_user": return "Updating user profile"
        case "update_user_preferences": return "Updating preferences"
        case "get_my_user_id": return "Checking user session"
        
        // Exercise database
        case "list_exercises": return "Browsing exercises"
        case "search_exercises": return "Searching exercises"
        case "get_exercise": return "Getting exercise details"
        
        // Workout tracking
        case "get_user_workouts": return "Loading workout history"
        case "get_workout": return "Getting workout details"
        
        // Template management
        case "get_user_templates": return "Fetching templates"
        case "get_template": return "Loading template"
        case "create_template": return "Creating new template"
        case "update_template": return "Updating template"
        case "delete_template": return "Deleting template"
        
        // Routine management
        case "get_user_routines": return "Loading routines"
        case "get_active_routine": return "Checking active routine"
        case "get_routine": return "Loading routine details"
        case "create_routine": return "Creating routine"
        case "update_routine": return "Updating routine"
        case "delete_routine": return "Deleting routine"
        case "set_active_routine": return "Activating routine"
        
        // Exercise admin
        case "upsert_exercise": return "Saving exercise"
        case "approve_exercise": return "Approving exercise"

        // Active workout
        case "propose_session": return "Proposing session"
        case "start_active_workout": return "Starting workout"
        case "get_active_workout": return "Loading active workout"
        case "prescribe_set": return "Prescribing set"
        case "log_set": return "Logging set"
        case "score_set": return "Scoring set"
        case "add_exercise": return "Adding exercise"
        case "swap_exercise": return "Swapping exercise"
        case "complete_active_workout": return "Completing workout"
        case "cancel_active_workout": return "Cancelling workout"
        case "note_active_workout": return "Adding note"

        // Memory management
        case "store_important_fact": return "Saving important information"
        case "get_important_facts": return "Recalling saved information"
        
        default: return "Processing"
        }
    }
    
    private func getHumanReadableFunctionResponseName(_ name: String) -> String {
        switch name {
        // User management
        case "get_user": return "User profile loaded"
        case "get_user_preferences": return "Preferences loaded"
        case "update_user": return "Profile updated"
        case "update_user_preferences": return "Preferences updated"
        case "get_my_user_id": return "Session verified"
        
        // Exercise database
        case "list_exercises": return "Exercises loaded"
        case "search_exercises": return "Search complete"
        case "get_exercise": return "Exercise details loaded"
        
        // Workout tracking
        case "get_user_workouts": return "Workout history loaded"
        case "get_workout": return "Workout details loaded"
        
        // Template management
        case "get_user_templates": return "Templates loaded"
        case "get_template": return "Template loaded"
        case "create_template": return "Template created"
        case "update_template": return "Template updated"
        case "delete_template": return "Template deleted"
        
        // Routine management
        case "get_user_routines": return "Routines loaded"
        case "get_active_routine": return "Active routine found"
        case "get_routine": return "Routine loaded"
        case "create_routine": return "Routine created"
        case "update_routine": return "Routine updated"
        case "delete_routine": return "Routine deleted"
        case "set_active_routine": return "Routine activated"
        
        // Exercise admin
        case "upsert_exercise": return "Exercise saved"
        case "approve_exercise": return "Exercise approved"

        // Active workout
        case "propose_session": return "Session proposed"
        case "start_active_workout": return "Workout started"
        case "get_active_workout": return "Active workout loaded"
        case "prescribe_set": return "Set prescribed"
        case "log_set": return "Set logged"
        case "score_set": return "Set scored"
        case "add_exercise": return "Exercise added"
        case "swap_exercise": return "Exercise swapped"
        case "complete_active_workout": return "Workout completed"
        case "cancel_active_workout": return "Workout cancelled"
        case "note_active_workout": return "Note added"

        // Memory management
        case "store_important_fact": return "Information saved"
        case "get_important_facts": return "Information recalled"
        
        default: return "Complete"
        }
    }
}

// MARK: - Error Types

enum StreamingError: LocalizedError {
    case notAuthenticated
    case tokenExchangeFailed
    case invalidTokenResponse
    case invalidResponse
    case sessionCreationFailed
    case invalidSessionResponse
    case listSessionsFailed
    case deleteSessionFailed
    case invalidURL
    case httpError(statusCode: Int)
    
    var errorDescription: String? {
        switch self {
        case .notAuthenticated:
            return "User not authenticated"
        case .tokenExchangeFailed:
            return "Failed to exchange Firebase token for GCP access token"
        case .invalidTokenResponse:
            return "Invalid token exchange response"
        case .invalidResponse:
            return "Invalid response from Agent Engine API"
        case .sessionCreationFailed:
            return "Failed to create session"
        case .invalidSessionResponse:
            return "Invalid session creation response"
        case .listSessionsFailed:
            return "Failed to list sessions"
        case .deleteSessionFailed:
            return "Failed to delete session"
        case .invalidURL:
            return "Invalid URL"
        case .httpError(let statusCode):
            return "HTTP error: \(statusCode)"
        }
    }
}
