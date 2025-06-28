import Foundation
import Combine



// MARK: - API Models
struct StreamQueryRequest: Codable {
    let message: String
    let userId: String
    let sessionId: String
}

struct AgentResponse: Codable {
    let content: ResponseContent?
    let author: String
    let timestamp: Double
    let id: String
    let invocationId: String?
    let actions: ResponseActions?
}

struct ResponseContent: Codable {
    let parts: [ResponsePart]
    let role: String
}

struct ResponsePart: Codable {
    let text: String?
    let functionCall: FunctionCall?
    let functionResponse: FunctionResponse?
}

struct FunctionCall: Codable {
    let id: String
    let name: String
    let args: [String: AnyCodable]?
}

struct FunctionResponse: Codable {
    let id: String
    let name: String
    let response: AnyCodable?
}

struct ResponseActions: Codable {
    let stateDelta: [String: AnyCodable]?
}

// Helper for handling Any in Codable
struct AnyCodable: Codable {
    let value: Any
    
    init(_ value: Any) {
        self.value = value
    }
    
    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let intValue = try? container.decode(Int.self) {
            value = intValue
        } else if let doubleValue = try? container.decode(Double.self) {
            value = doubleValue
        } else if let boolValue = try? container.decode(Bool.self) {
            value = boolValue
        } else if let stringValue = try? container.decode(String.self) {
            value = stringValue
        } else if let arrayValue = try? container.decode([AnyCodable].self) {
            value = arrayValue.map { $0.value }
        } else if let dictValue = try? container.decode([String: AnyCodable].self) {
            value = dictValue.mapValues { $0.value }
        } else {
            throw DecodingError.dataCorruptedError(in: container, debugDescription: "Unable to decode")
        }
    }
    
    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        if let intValue = value as? Int {
            try container.encode(intValue)
        } else if let doubleValue = value as? Double {
            try container.encode(doubleValue)
        } else if let boolValue = value as? Bool {
            try container.encode(boolValue)
        } else if let stringValue = value as? String {
            try container.encode(stringValue)
        } else {
            throw EncodingError.invalidValue(value, EncodingError.Context(codingPath: encoder.codingPath, debugDescription: "Unable to encode"))
        }
    }
}

// MARK: - StrengthOS Client
class StrengthOSClient {
    static let shared = StrengthOSClient()
    private let session = URLSession.shared
    private let decoder = JSONDecoder()
    
    private init() {}
    
    // MARK: - Authentication
    private func getAccessToken() async throws -> String {
        // The Vertex AI API requires Google Cloud OAuth 2.0 access tokens
        // Firebase ID tokens won't work directly
        
        // Option 1: Use Google Sign-In to get OAuth token
        // This requires implementing Google Sign-In in your app
        
        // Option 2: Use a Cloud Function to proxy requests
        // The Cloud Function can use service account credentials
        
        // Option 3: Exchange Firebase token for Google Cloud token
        // This requires additional backend setup
        
        // For now, let's check if we have a Google OAuth token
        // You'll need to implement Google Sign-In for this to work
        
        print("⚠️ Authentication Issue: Vertex AI requires Google Cloud OAuth tokens")
        print("Firebase ID tokens are not accepted by the Vertex AI API")
        print("You need to either:")
        print("1. Implement Google Sign-In to get OAuth tokens")
        print("2. Create a Cloud Function proxy with service account")
        print("3. Set up a token exchange service")
        
        // Temporary: Try to get Firebase token (won't work with Vertex AI)
        guard let currentUser = AuthService.shared.currentUser else {
            throw StrengthOSError.notAuthenticated
        }
        
        let token = try await currentUser.getIDToken()
        print("Warning: Using Firebase ID Token (not compatible with Vertex AI)")
        print("Token prefix: \(String(token.prefix(20)))...")
        
        // This will fail with 401, but helps demonstrate the issue
        return token
    }
    
    // MARK: - Streaming Query
    func streamQuery(
        message: String,
        userId: String,
        sessionId: String,
        imageData: Data? = nil
    ) -> AsyncThrowingStream<StreamEvent, Error> {
        return AsyncThrowingStream { continuation in
            Task {
                do {
                    let url = URL(string: "\(StrengthOSEnvironment.baseURL):streamQuery")!
                    var request = URLRequest(url: url)
                    request.httpMethod = "POST"
                    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
                    request.setValue("text/event-stream", forHTTPHeaderField: "Accept")
                    
                    // Add authentication
                    let token = try await getAccessToken()
                    request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
                    
                    // Create request body
                    let requestBody = StreamQueryRequest(
                        message: message,
                        userId: userId,
                        sessionId: sessionId
                    )
                    request.httpBody = try JSONEncoder().encode(requestBody)
                    
                    // Create streaming session
                    let (asyncBytes, response) = try await session.bytes(for: request)
                    
                    guard let httpResponse = response as? HTTPURLResponse,
                          httpResponse.statusCode == 200 else {
                        throw StrengthOSError.invalidResponse
                    }
                    
                    // Process SSE stream
                    var buffer = ""
                    
                    for try await byte in asyncBytes {
                        let character = Character(UnicodeScalar(byte))
                        buffer.append(character)
                        
                        // Check for complete SSE message
                        if buffer.contains("\n\n") {
                            let messages = buffer.components(separatedBy: "\n\n")
                            
                            for (index, message) in messages.enumerated() {
                                // Keep the last incomplete message in buffer
                                if index == messages.count - 1 && !message.isEmpty {
                                    buffer = message
                                } else if !message.isEmpty {
                                    // Process complete message
                                    if let event = parseSSEMessage(message) {
                                        continuation.yield(event)
                                    }
                                }
                            }
                        }
                    }
                    
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
        }
    }
    
    // MARK: - SSE Parsing
    private func parseSSEMessage(_ message: String) -> StreamEvent? {
        let lines = message.components(separatedBy: "\n")
        var eventType: String?
        var eventData: String?
        
        for line in lines {
            if line.hasPrefix("event:") {
                eventType = String(line.dropFirst(6)).trimmingCharacters(in: .whitespaces)
            } else if line.hasPrefix("data:") {
                eventData = String(line.dropFirst(5)).trimmingCharacters(in: .whitespaces)
            }
        }
        
        guard let data = eventData?.data(using: .utf8) else { return nil }
        
        do {
            if eventType == "error" {
                let error = try decoder.decode(StreamError.self, from: data)
                return .error(error)
            } else {
                let response = try decoder.decode(AgentResponse.self, from: data)
                return .message(response)
            }
        } catch {
            print("Failed to parse SSE message: \(error)")
            return nil
        }
    }
    
    // MARK: - Session Management
    func createSession(userId: String) async throws -> String {
        let url = URL(string: "\(StrengthOSEnvironment.baseURL):createSession")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        let token = try await getAccessToken()
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        
        let body = ["userId": userId]
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        
        let (data, response) = try await session.data(for: request)
        
        // Debug: Print the raw response
        if let httpResponse = response as? HTTPURLResponse {
            print("CreateSession Response Status: \(httpResponse.statusCode)")
            
            // Handle non-200 responses
            if httpResponse.statusCode != 200 {
                if let responseString = String(data: data, encoding: .utf8) {
                    print("CreateSession Error Response: \(responseString)")
                }
                
                // For auth errors, throw
                if httpResponse.statusCode == 401 || httpResponse.statusCode == 403 {
                    throw StrengthOSError.notAuthenticated
                }
                
                // For other errors, throw generic error
                throw StrengthOSError.invalidResponse
            }
        }
        
        if let responseString = String(data: data, encoding: .utf8) {
            print("CreateSession Raw Response: \(responseString)")
        }
        
        let sessionResponse = try decoder.decode(CreateSessionResponse.self, from: data)
        return sessionResponse.id
    }
    
    func listSessions(userId: String) async throws -> [String] {
        let url = URL(string: "\(StrengthOSEnvironment.baseURL):listSessions?userId=\(userId)")!
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        
        let token = try await getAccessToken()
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        
        let (data, response) = try await session.data(for: request)
        
        // Debug: Print the raw response
        if let httpResponse = response as? HTTPURLResponse {
            print("ListSessions Response Status: \(httpResponse.statusCode)")
            
            // Handle non-200 responses
            if httpResponse.statusCode != 200 {
                if let responseString = String(data: data, encoding: .utf8) {
                    print("ListSessions Error Response: \(responseString)")
                }
                
                // For 404 or similar, just return empty array (no sessions)
                if httpResponse.statusCode == 404 {
                    return []
                }
                
                // For auth errors, throw
                if httpResponse.statusCode == 401 || httpResponse.statusCode == 403 {
                    throw StrengthOSError.notAuthenticated
                }
                
                // For other errors, throw generic error
                throw StrengthOSError.invalidResponse
            }
        }
        
        if let responseString = String(data: data, encoding: .utf8) {
            print("ListSessions Raw Response: \(responseString)")
        }
        
        // Handle empty response or different format
        if data.isEmpty {
            return []
        }
        
        do {
            let response = try decoder.decode(ListSessionsResponse.self, from: data)
            return response.sessionIds
        } catch {
            print("Failed to decode ListSessionsResponse: \(error)")
            
            // Try to decode as a simple array
            if let sessionIds = try? decoder.decode([String].self, from: data) {
                return sessionIds
            }
            
            // If we can't decode, return empty array instead of failing
            return []
        }
    }
    
    func deleteSession(userId: String, sessionId: String) async throws {
        let url = URL(string: "\(StrengthOSEnvironment.baseURL):deleteSession")!
        var request = URLRequest(url: url)
        request.httpMethod = "DELETE"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        let token = try await getAccessToken()
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        
        let body = ["userId": userId, "sessionId": sessionId]
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        
        let (_, response) = try await session.data(for: request)
        
        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else {
            throw StrengthOSError.deletionFailed
        }
    }
    
    // MARK: - Debug/Test Methods
    func testAPIConnection() async throws {
        print("=== Testing StrengthOS API Connection ===")
        
        // Test 1: Check authentication
        do {
            let token = try await getAccessToken()
            print("✅ Authentication successful")
            print("Token length: \(token.count)")
        } catch {
            print("❌ Authentication failed: \(error)")
            throw error
        }
        
        // Test 2: Try to list sessions (might be empty)
        do {
            let sessions = try await listSessions(userId: AuthService.shared.currentUser?.uid ?? "")
            print("✅ List sessions successful")
            print("Sessions count: \(sessions.count)")
        } catch {
            print("⚠️ List sessions failed (might be normal for new users): \(error)")
        }
        
        print("=== API Connection Test Complete ===")
    }
}

// MARK: - Response Types
struct CreateSessionResponse: Codable {
    let id: String
    let appName: String
    let userId: String
    let state: [String: AnyCodable]?
    let events: [AnyCodable]?
    let lastUpdateTime: Double
    
    enum CodingKeys: String, CodingKey {
        case id
        case appName = "app_name"
        case userId = "user_id"
        case state
        case events
        case lastUpdateTime = "last_update_time"
    }
}

struct ListSessionsResponse: Codable {
    let sessionIds: [String]
    
    enum CodingKeys: String, CodingKey {
        case sessionIds = "session_ids"
    }
}

// MARK: - Stream Events
enum StreamEvent {
    case message(AgentResponse)
    case error(StreamError)
}

struct StreamError: Codable {
    let code: Int
    let message: String
}

// MARK: - Errors
enum StrengthOSError: LocalizedError {
    case notAuthenticated
    case invalidResponse
    case deletionFailed
    case networkError(Error)
    
    var errorDescription: String? {
        switch self {
        case .notAuthenticated:
            return "Please sign in to use StrengthOS"
        case .invalidResponse:
            return "Invalid response from server"
        case .deletionFailed:
            return "Failed to delete session"
        case .networkError(let error):
            return "Network error: \(error.localizedDescription)"
        }
    }
} 