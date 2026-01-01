import Foundation

enum StrengthOSError: LocalizedError {
    case notAuthenticated
    case invalidResponse
    case deletionFailed
    case networkError(Error)

    var errorDescription: String? {
        switch self {
        case .notAuthenticated:
            return "Please sign in to continue."
        case .invalidResponse:
            return "Invalid response from server."
        case .deletionFailed:
            return "Failed to delete resource."
        case .networkError(let error):
            return "Network error: \(error.localizedDescription)"
        }
    }
}


