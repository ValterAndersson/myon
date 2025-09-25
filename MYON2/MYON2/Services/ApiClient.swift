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
        guard let user = Auth.auth().currentUser else { throw NSError(domain: "ApiClient", code: 401, userInfo: [NSLocalizedDescriptionKey: "Not authenticated"]) }
        let idToken = try await user.getIDToken()
        request.setValue("Bearer \(idToken)", forHTTPHeaderField: "Authorization")

        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        request.httpBody = try encoder.encode(body)

        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601

        // Simple retry with jitter for transient errors
        var attempt = 0
        let maxAttempts = 3
        var lastError: Error?
        while attempt < maxAttempts {
            do {
                if DebugLogger.enabled {
                    let headers = request.allHTTPHeaderFields ?? [:]
                    DebugLogger.debug(.network, "➡️ POST \(request.url?.absoluteString ?? path)\nHeaders: \(DebugLogger.sanitizeHeaders(headers))\nBody:\n\(DebugLogger.prettyJSON(body))")
                }
                let (data, response) = try await session.data(for: request)
                guard let http = response as? HTTPURLResponse else { throw NSError(domain: "ApiClient", code: -1, userInfo: [NSLocalizedDescriptionKey: "No HTTP response"]) }
                if (200...299).contains(http.statusCode) {
                    let decoded = try decoder.decode(R.self, from: data)
                    if DebugLogger.enabled {
                        DebugLogger.debug(.network, "✅ \(http.statusCode) \(request.url?.lastPathComponent ?? path)\nResponse:\n\(String(data: data, encoding: .utf8) ?? "<binary>")")
                    }
                    return decoded
                }
                // Allow decoding to R for normalized error envelopes
                if let result = try? decoder.decode(R.self, from: data) {
                    if DebugLogger.enabled {
                        DebugLogger.error(.network, "⚠️ \(http.statusCode) \(request.url?.lastPathComponent ?? path) decoded error envelope")
                    }
                    return result
                }
                // 5xx → retry; 429 → retry; others → throw
                if http.statusCode >= 500 || http.statusCode == 429 {
                    throw NSError(domain: "ApiClient", code: http.statusCode, userInfo: [NSLocalizedDescriptionKey: "HTTP \(http.statusCode)"])
                } else {
                    // Decode normalized error body for user-friendly message if available
                    if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                       let err = json["error"] as? [String: Any],
                       let code = err["code"] as? String,
                       let message = err["message"] as? String {
                        let nsErr = NSError(domain: "ApiClient", code: http.statusCode, userInfo: ["code": code, NSLocalizedDescriptionKey: message])
                        throw nsErr
                    }
                    if DebugLogger.enabled {
                        DebugLogger.error(.network, "❌ \(http.statusCode) \(request.url?.lastPathComponent ?? path)\nBody:\n\(String(data: data, encoding: .utf8) ?? "<binary>")")
                    }
                    throw NSError(domain: "ApiClient", code: http.statusCode, userInfo: [NSLocalizedDescriptionKey: "HTTP \(http.statusCode)"])
                }
            } catch {
                lastError = error
                attempt += 1
                if attempt >= maxAttempts { break }
                let backoff = Double.random(in: 0.15...0.35) * pow(2.0, Double(attempt - 1))
                try? await Task.sleep(nanoseconds: UInt64(backoff * 1_000_000_000))
            }
        }
        if DebugLogger.enabled {
            DebugLogger.error(.network, "❌ Final failure POST \(path): \(lastError?.localizedDescription ?? "Unknown error")")
        }
        throw lastError ?? NSError(domain: "ApiClient", code: -1, userInfo: [NSLocalizedDescriptionKey: "Unknown error"])
    }
}


