import Foundation

// MARK: - Subscription Tier

/// Available subscription tiers
enum SubscriptionTier: String, Codable {
    case free = "free"
    case premium = "premium"
}

// MARK: - Subscription Status

/// Current state of a user's subscription
enum SubscriptionStatusValue: String, Codable {
    case free = "free"
    case trial = "trial"
    case active = "active"
    case expired = "expired"
    case gracePeriod = "grace_period"
}

// MARK: - User Subscription State

/// Aggregated subscription state for UI and gate checks.
/// Named UserSubscriptionState to avoid conflict with Product.SubscriptionInfo from StoreKit.
struct UserSubscriptionState {
    var tier: SubscriptionTier
    var status: SubscriptionStatusValue
    var override: String?          // "premium" | nil — admin override for test/beta users
    var expiresAt: Date?
    var autoRenewEnabled: Bool
    var inGracePeriod: Bool
    var productId: String?
    var originalTransactionId: String?
    var appAccountToken: String?

    /// Returns true if the user has active premium access (via override or subscription)
    var isPremium: Bool {
        if override == "premium" { return true }
        return tier == .premium
    }

    /// Default free state for new/unauthenticated users
    static let free = UserSubscriptionState(
        tier: .free,
        status: .free,
        override: nil,
        expiresAt: nil,
        autoRenewEnabled: false,
        inGracePeriod: false,
        productId: nil,
        originalTransactionId: nil,
        appAccountToken: nil
    )
}
