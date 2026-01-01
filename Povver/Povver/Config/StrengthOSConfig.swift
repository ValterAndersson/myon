import Foundation

// MARK: - StrengthOS Configuration
struct StrengthOSEnvironment {
    // These values are from the README documentation
    static let projectId = "919326069447"
    static let location = "us-central1"  // Only supported region for Agent Engine Sessions
    static let agentId = "4683295011721183232"
    static let projectName = "myon-53d85"
    
    // Base URL for the API
    static var baseURL: String {
        "https://\(location)-aiplatform.googleapis.com/v1/projects/\(projectId)/locations/\(location)/reasoningEngines/\(agentId)"
    }
    
    // Firebase API Key (if needed for direct Firebase calls)
    // This would typically come from your GoogleService-Info.plist
    static var firebaseAPIKey: String? {
        // Read from bundle if needed
        return Bundle.main.object(forInfoDictionaryKey: "FIREBASE_API_KEY") as? String
    }
    
    // Check if we're properly configured
    static var isConfigured: Bool {
        // For now, we just need Firebase Auth to be configured
        // The actual API key exchange happens through Firebase Auth tokens
        return true
    }
    
    // Development vs Production
    #if DEBUG
    static let isDevelopment = true
    #else
    static let isDevelopment = false
    #endif
} 