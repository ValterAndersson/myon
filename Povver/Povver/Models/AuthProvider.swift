import SwiftUI

/// Maps Firebase provider IDs to app-level provider identifiers.
/// `rawValue` matches Firebase's `providerData[].providerID` strings, used for
/// `unlink(fromProvider:)` and provider lookups. The Firestore `provider` field
/// uses these same values except email sign-ups write `"email"` (not `"password"`).
enum AuthProvider: String, CaseIterable, Identifiable {
    case email = "password"       // Firebase's internal ID for email/password
    case google = "google.com"
    case apple = "apple.com"

    var id: String { rawValue }

    var displayName: String {
        switch self {
        case .email: return "Email"
        case .google: return "Google"
        case .apple: return "Apple"
        }
    }

    var icon: Image {
        switch self {
        case .email: return Image(systemName: "envelope")
        case .google: return Image(systemName: "globe")
        case .apple: return Image(systemName: "apple.logo")
        }
    }

    /// Value written to the Firestore `provider` field on account creation.
    /// Email uses "email" (human-readable) instead of Firebase's "password" ID.
    var firestoreValue: String {
        switch self {
        case .email: return "email"
        case .google: return "google.com"
        case .apple: return "apple.com"
        }
    }

    /// Maps a Firebase `providerData[].providerID` string to an AuthProvider.
    static func from(_ firebaseProviderId: String) -> AuthProvider? {
        return AuthProvider(rawValue: firebaseProviderId)
    }
}
