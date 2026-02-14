import Foundation
import FirebaseFirestore

struct User: Codable {
    var name: String?
    var email: String
    var provider: String
    var uid: String
    var createdAt: Date
    var weekStartsOnMonday: Bool = true  // Default to Monday
    var timeZone: String? // e.g. "Europe/Helsinki", "America/New_York"
    var appleAuthorizationCode: String? // Stored on first Apple Sign-In, needed for token revocation on account deletion

    enum CodingKeys: String, CodingKey {
        case name
        case email
        case provider
        case uid
        case createdAt = "created_at"
        case weekStartsOnMonday = "week_starts_on_monday"
        case timeZone = "timezone"
        case appleAuthorizationCode = "apple_authorization_code"
    }
} 