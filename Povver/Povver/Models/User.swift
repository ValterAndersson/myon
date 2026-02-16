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

    // Subscription fields — flat to match Firestore schema.
    // Gate check: isPremium = (subscriptionOverride == "premium") OR (subscriptionTier == "premium")
    var subscriptionStatus: String?    // free | trial | active | expired | grace_period
    var subscriptionTier: String?      // free | premium
    var subscriptionOverride: String?  // "premium" | nil — admin override for test/beta users
    var subscriptionExpiresAt: Date?
    var autoPilotEnabled: Bool = false

    enum CodingKeys: String, CodingKey {
        case name
        case email
        case provider
        case uid
        case createdAt = "created_at"
        case weekStartsOnMonday = "week_starts_on_monday"
        case timeZone = "timezone"
        case appleAuthorizationCode = "apple_authorization_code"
        case subscriptionStatus = "subscription_status"
        case subscriptionTier = "subscription_tier"
        case subscriptionOverride = "subscription_override"
        case subscriptionExpiresAt = "subscription_expires_at"
        case autoPilotEnabled = "auto_pilot_enabled"
    }

    /// Returns true if the user has active premium access (via admin override or subscription)
    var isPremium: Bool {
        if subscriptionOverride == "premium" { return true }
        return subscriptionTier == "premium"
    }
}
