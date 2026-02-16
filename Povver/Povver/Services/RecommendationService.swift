import Foundation

struct ReviewRecommendationRequest: Encodable {
    let recommendationId: String
    let action: String
}

/// Matches normalized response envelope from `utils/response.js`:
/// Success: `{ success: true, data: { status: "applied" } }`
/// Error: `{ success: false, error: { code: "STALE_RECOMMENDATION", message: "..." } }`
struct ReviewRecommendationResponse: Decodable {
    let success: Bool
    let data: ReviewResult?
    let error: ErrorDetail?

    struct ReviewResult: Decodable {
        let status: String
    }

    struct ErrorDetail: Decodable {
        let code: String
        let message: String
    }
}

enum RecommendationService {
    static func review(recommendationId: String, action: String) async throws -> ReviewRecommendationResponse {
        try await ApiClient.shared.postJSON(
            "reviewRecommendation",
            body: ReviewRecommendationRequest(
                recommendationId: recommendationId,
                action: action
            )
        )
    }
}
