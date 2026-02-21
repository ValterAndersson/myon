import Foundation
import FirebaseAuth

final class ApiClient {
    static let shared = ApiClient()
    private let baseURL = URL(string: "https://us-central1-myon-53d85.cloudfunctions.net")!
    private let session: URLSession = .shared

    func postJSON<T: Encodable, R: Decodable>(_ path: String, body: T) async throws -> R {
        var request = URLRequest(url: baseURL.appendingPathComponent(path))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        // Firebase ID token
        guard let user = Auth.auth().currentUser else {
            AppLogger.shared.error(.http, "Not authenticated for \(path)")
            throw NSError(domain: "ApiClient", code: 401, userInfo: [NSLocalizedDescriptionKey: "Not authenticated"])
        }
        let idToken = try await user.getIDToken()
        request.setValue("Bearer \(idToken)", forHTTPHeaderField: "Authorization")

        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        encoder.outputFormatting = [.sortedKeys]
        let bodyData = try encoder.encode(body)
        request.httpBody = bodyData

        // HTTP correlation ID
        var rid = AppLogger.shared.httpReq(method: "POST", endpoint: path)

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
                    AppLogger.shared.httpRes(rid: rid, status: http.statusCode, ms: durationMs, endpoint: path, body: responseBody)

                    return decoded
                }

                // Allow decoding to R for normalized error envelopes
                if let result = try? decoder.decode(R.self, from: data) {
                    AppLogger.shared.httpRes(rid: rid, status: http.statusCode, ms: durationMs, endpoint: path, body: responseBody)
                    return result
                }

                // 5xx → retry; 429 → retry; others → throw
                if http.statusCode >= 500 || http.statusCode == 429 {
                    AppLogger.shared.info(.http, "retry \(attempt+1)/\(maxAttempts) \(path) HTTP \(http.statusCode)")
                    throw NSError(domain: "ApiClient", code: http.statusCode, userInfo: [NSLocalizedDescriptionKey: "HTTP \(http.statusCode)"])
                } else {
                    // Decode normalized error body for user-friendly message if available
                    if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                       let err = json["error"] as? [String: Any],
                       let code = err["code"] as? String,
                       let message = err["message"] as? String {

                        let error = NSError(domain: "ApiClient", code: http.statusCode, userInfo: [NSLocalizedDescriptionKey: "\(code): \(message)"])
                        AppLogger.shared.httpRes(rid: rid, status: http.statusCode, ms: durationMs, endpoint: path, error: error)

                        throw NSError(domain: "ApiClient", code: http.statusCode, userInfo: ["code": code, NSLocalizedDescriptionKey: message])
                    }

                    let error = NSError(domain: "ApiClient", code: http.statusCode, userInfo: [NSLocalizedDescriptionKey: "HTTP \(http.statusCode)"])
                    AppLogger.shared.httpRes(rid: rid, status: http.statusCode, ms: durationMs, endpoint: path, error: error)

                    throw error
                }
            } catch {
                lastError = error
                attempt += 1

                if attempt >= maxAttempts {
                    AppLogger.shared.error(.http, "\(path) failed after \(maxAttempts) attempts", lastError)
                    break
                }

                let backoff = Double.random(in: 0.15...0.35) * pow(2.0, Double(attempt - 1))
                AppLogger.shared.info(.http, "retry \(attempt)/\(maxAttempts) for \(path) backoff=\(String(format: "%.2f", backoff))s")

                // Get new correlation ID for retry
                rid = AppLogger.shared.httpReq(method: "POST", endpoint: "\(path) (retry \(attempt)/\(maxAttempts))")

                try? await Task.sleep(nanoseconds: UInt64(backoff * 1_000_000_000))
            }
        }

        throw lastError ?? NSError(domain: "ApiClient", code: -1, userInfo: [NSLocalizedDescriptionKey: "Unknown error"])
    }
}
