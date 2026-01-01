import Foundation
import FirebaseAuth

// =============================================================================
// MARK: - ApiClient.swift - HTTP Client with Comprehensive Logging
// =============================================================================
//
// PURPOSE:
// Core HTTP client for Firebase Functions. All HTTP calls to the backend
// flow through here, which makes it the ideal place for centralized logging.
//
// LOGGING:
// Uses SessionLogger to produce verbose, structured output including:
// - Full request body (JSON formatted)
// - Full response body (JSON formatted)
// - HTTP status codes
// - Timing (ms)
// - Retry attempts
// - Error details
//
// =============================================================================

final class ApiClient {
    static let shared = ApiClient()
    private let baseURL = URL(string: "https://us-central1-myon-53d85.cloudfunctions.net")!
    private let session: URLSession = .shared

    func postJSON<T: Encodable, R: Decodable>(_ path: String, body: T) async throws -> R {
        let startTime = Date()
        var request = URLRequest(url: baseURL.appendingPathComponent(path))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        // Firebase ID token
        guard let user = Auth.auth().currentUser else {
            SessionLogger.shared.logError(
                category: .http,
                message: "Not authenticated - cannot make HTTP request",
                context: ["path": path]
            )
            throw NSError(domain: "ApiClient", code: 401, userInfo: [NSLocalizedDescriptionKey: "Not authenticated"])
        }
        let idToken = try await user.getIDToken()
        request.setValue("Bearer \(idToken)", forHTTPHeaderField: "Authorization")

        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        encoder.outputFormatting = [.sortedKeys]
        let bodyData = try encoder.encode(body)
        request.httpBody = bodyData
        
        // Log the request with full body
        if let bodyDict = try? JSONSerialization.jsonObject(with: bodyData) {
            SessionLogger.shared.logHTTPRequest(
                method: "POST",
                endpoint: path,
                headers: DebugLogger.sanitizeHeaders(request.allHTTPHeaderFields ?? [:]),
                body: bodyDict
            )
        } else {
            SessionLogger.shared.logHTTPRequest(
                method: "POST",
                endpoint: path,
                headers: DebugLogger.sanitizeHeaders(request.allHTTPHeaderFields ?? [:]),
                body: String(data: bodyData, encoding: .utf8) ?? "<binary>"
            )
        }

        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601

        // Simple retry with jitter for transient errors
        var attempt = 0
        let maxAttempts = 3
        var lastError: Error?
        
        while attempt < maxAttempts {
            let attemptStart = Date()
            do {
                let (data, response) = try await session.data(for: request)
                let durationMs = Int(Date().timeIntervalSince(attemptStart) * 1000)
                
                guard let http = response as? HTTPURLResponse else {
                    throw NSError(domain: "ApiClient", code: -1, userInfo: [NSLocalizedDescriptionKey: "No HTTP response"])
                }
                
                // Parse response body for logging
                let responseBody: Any
                if let jsonObject = try? JSONSerialization.jsonObject(with: data) {
                    responseBody = jsonObject
                } else {
                    responseBody = String(data: data, encoding: .utf8) ?? "<binary>"
                }
                
                if (200...299).contains(http.statusCode) {
                    let decoded = try decoder.decode(R.self, from: data)
                    
                    // Log successful response
                    SessionLogger.shared.logHTTPResponse(
                        method: "POST",
                        endpoint: path,
                        statusCode: http.statusCode,
                        durationMs: durationMs,
                        body: responseBody
                    )
                    
                    return decoded
                }
                
                // Allow decoding to R for normalized error envelopes
                if let result = try? decoder.decode(R.self, from: data) {
                    SessionLogger.shared.logHTTPResponse(
                        method: "POST",
                        endpoint: path,
                        statusCode: http.statusCode,
                        durationMs: durationMs,
                        body: responseBody
                    )
                    return result
                }
                
                // 5xx → retry; 429 → retry; others → throw
                if http.statusCode >= 500 || http.statusCode == 429 {
                    SessionLogger.shared.log(.http, .warning, "Retryable error \(http.statusCode) for \(path) (attempt \(attempt + 1)/\(maxAttempts))")
                    throw NSError(domain: "ApiClient", code: http.statusCode, userInfo: [NSLocalizedDescriptionKey: "HTTP \(http.statusCode)"])
                } else {
                    // Decode normalized error body for user-friendly message if available
                    if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                       let err = json["error"] as? [String: Any],
                       let code = err["code"] as? String,
                       let message = err["message"] as? String {
                        
                        SessionLogger.shared.logHTTPResponse(
                            method: "POST",
                            endpoint: path,
                            statusCode: http.statusCode,
                            durationMs: durationMs,
                            body: responseBody,
                            error: NSError(domain: "ApiClient", code: http.statusCode, userInfo: [NSLocalizedDescriptionKey: "\(code): \(message)"])
                        )
                        
                        throw NSError(domain: "ApiClient", code: http.statusCode, userInfo: ["code": code, NSLocalizedDescriptionKey: message])
                    }
                    
                    SessionLogger.shared.logHTTPResponse(
                        method: "POST",
                        endpoint: path,
                        statusCode: http.statusCode,
                        durationMs: durationMs,
                        body: responseBody
                    )
                    
                    throw NSError(domain: "ApiClient", code: http.statusCode, userInfo: [NSLocalizedDescriptionKey: "HTTP \(http.statusCode)"])
                }
            } catch {
                lastError = error
                attempt += 1
                
                if attempt >= maxAttempts {
                    let totalDuration = Int(Date().timeIntervalSince(startTime) * 1000)
                    SessionLogger.shared.logError(
                        category: .http,
                        message: "HTTP request failed after \(maxAttempts) attempts",
                        error: error,
                        context: [
                            "path": path,
                            "attempts": attempt,
                            "total_duration_ms": totalDuration
                        ]
                    )
                    break
                }
                
                let backoff = Double.random(in: 0.15...0.35) * pow(2.0, Double(attempt - 1))
                SessionLogger.shared.log(.http, .debug, "Retry \(attempt)/\(maxAttempts) for \(path) after \(String(format: "%.2f", backoff))s")
                try? await Task.sleep(nanoseconds: UInt64(backoff * 1_000_000_000))
            }
        }
        
        throw lastError ?? NSError(domain: "ApiClient", code: -1, userInfo: [NSLocalizedDescriptionKey: "Unknown error"])
    }
}
