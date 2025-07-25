import Foundation
import Combine

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
    private let projectId = "myon-53d85"
    private let location = "us-central1"
    private let reasoningEngineId = "4683295011721183232"
    
    private var gcpAuthToken: String?
    private var tokenExpiryTime: Date?
    
    private let session = URLSession(configuration: .default)
    
    // MARK: - Public Methods
    
    /// Query the agent with streaming response
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
                
                // Build the request
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
                
                // Create streaming task
                let (asyncBytes, response) = try await session.bytes(for: request)
                
                guard let httpResponse = response as? HTTPURLResponse,
                      httpResponse.statusCode == 200 else {
                    throw StreamingError.invalidResponse
                }
                
                var fullResponse = ""
                var returnedSessionId: String?
                
                // Process streaming response
                for try await line in asyncBytes.lines {
                    print("🪵 SSE:", line)
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
                                    // Accumulate text instead of overwriting
                                    if !text.isEmpty {
                                        fullResponse += text
                                        // Pass the accumulated response
                                        progressHandler(fullResponse, nil)
                                    }
                                }
                                
                                // Handle function calls
                                if let functionCall = part["function_call"] as? [String: Any],
                                   let name = functionCall["name"] as? String {
                                    let args = functionCall["args"] as? [String: Any]
                                    let argsString = formatFunctionArgs(args)
                                    let humanReadableName = getHumanReadableFunctionName(name)
                                    progressHandler(nil, "\(humanReadableName)\(argsString)")
                                }
                                
                                // Handle function responses
                                if let functionResponse = part["function_response"] as? [String: Any],
                                   let name = functionResponse["name"] as? String {
                                    let humanReadableName = getHumanReadableFunctionResponseName(name)
                                    
                                    // Try to extract useful info from response
                                    if let response = functionResponse["response"] as? String,
                                       let responseData = response.data(using: .utf8),
                                       let responseJson = try? JSONSerialization.jsonObject(with: responseData) as? [String: Any] {
                                        
                                        // Extract counts or relevant info based on function
                                        var responseDetail = ""
                                        switch name {
                                        case "get_user_templates":
                                            if let data = responseJson["data"] as? [[String: Any]] {
                                                responseDetail = " - found \(data.count) template\(data.count == 1 ? "" : "s")"
                                            }
                                        case "get_user_workouts":
                                            if let data = responseJson["data"] as? [[String: Any]] {
                                                responseDetail = " - found \(data.count) workout\(data.count == 1 ? "" : "s")"
                                            }
                                        case "search_exercises", "list_exercises":
                                            if let data = responseJson["data"] as? [[String: Any]] {
                                                responseDetail = " - found \(data.count) exercise\(data.count == 1 ? "" : "s")"
                                            }
                                        case "get_user_routines":
                                            if let data = responseJson["data"] as? [[String: Any]] {
                                                responseDetail = " - found \(data.count) routine\(data.count == 1 ? "" : "s")"
                                            }
                                        default:
                                            break
                                        }
                                        progressHandler(nil, "\(humanReadableName)\(responseDetail)")
                                    } else {
                                        progressHandler(nil, humanReadableName)
                                    }
                                }
                            }
                        }
                    }
                }
                
                completion(.success((fullResponse, returnedSessionId ?? sessionId)))
                
            } catch {
                completion(.failure(error))
            }
        }
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
        if let templateId = args["template_id"] as? String {
            displayParts.append("template")
        }
        if let workoutId = args["workout_id"] as? String {
            displayParts.append("workout")
        }
        if let routineId = args["routine_id"] as? String {
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
        case "update_user": return "Updating user profile"
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
        case "update_user": return "Profile updated"
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