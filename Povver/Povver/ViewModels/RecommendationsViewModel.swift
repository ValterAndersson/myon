import Foundation
import Combine

@MainActor
class RecommendationsViewModel: ObservableObject {
    @Published var pendingCount: Int = 0
    @Published var pending: [AgentRecommendation] = []
    @Published var recent: [AgentRecommendation] = []
    @Published var isProcessing: Bool = false
    @Published var errorMessage: String?

    private let repository = RecommendationRepository.shared
    private var cancellables = Set<AnyCancellable>()

    init() {
        repository.$recommendations
            .receive(on: DispatchQueue.main)
            .sink { [weak self] recs in
                guard let self = self else { return }
                self.pending = recs.filter { $0.state == "pending_review" }
                self.recent = Array(recs.filter { $0.state == "applied" || $0.state == "acknowledged" }.prefix(10))
                self.pendingCount = self.pending.count
            }
            .store(in: &cancellables)
    }

    func startListening(userId: String) {
        guard SubscriptionService.shared.isPremium else { return }
        repository.startListening(userId: userId)
    }

    func stopListening() {
        repository.stopListening()
        pending = []
        recent = []
        pendingCount = 0
    }

    func accept(_ recommendation: AgentRecommendation) {
        guard let id = recommendation.id else { return }
        isProcessing = true
        errorMessage = nil

        // Optimistic removal
        pending.removeAll { $0.id == id }
        pendingCount = pending.count

        let recType = recommendation.recommendation.type

        Task {
            do {
                let response = try await RecommendationService.review(
                    recommendationId: id,
                    action: "accept"
                )
                if !response.success {
                    handleServerError(response.error)
                } else {
                    AnalyticsService.shared.recommendationAccepted(type: recType, scope: recommendation.scope)
                }
            } catch {
                handleThrownError(error)
            }
            isProcessing = false
        }
    }

    func reject(_ recommendation: AgentRecommendation) {
        guard let id = recommendation.id else { return }
        isProcessing = true
        errorMessage = nil

        // Optimistic removal
        pending.removeAll { $0.id == id }
        pendingCount = pending.count

        let recType = recommendation.recommendation.type

        Task {
            do {
                let response = try await RecommendationService.review(
                    recommendationId: id,
                    action: "reject"
                )
                if !response.success {
                    handleServerError(response.error)
                } else {
                    AnalyticsService.shared.recommendationRejected(type: recType, scope: recommendation.scope)
                }
            } catch {
                handleThrownError(error)
            }
            isProcessing = false
        }
    }

    // MARK: - Error Handling

    /// Handle structured error from server response envelope (non-2xx that decoded successfully).
    /// ApiClient returns decoded response for 4xx when JSON matches the response struct.
    private func handleServerError(_ error: ReviewRecommendationResponse.ErrorDetail?) {
        guard let error = error else {
            errorMessage = "Failed to apply recommendation."
            return
        }
        switch error.code {
        case "STALE_RECOMMENDATION":
            errorMessage = "This recommendation is outdated — your template was changed since it was created."
        case "PREMIUM_REQUIRED":
            stopListening()
            errorMessage = "Premium subscription required."
        default:
            errorMessage = error.message
        }
    }

    /// Handle errors thrown by ApiClient (network failures, non-decodable error responses).
    private func handleThrownError(_ error: Error) {
        let nsError = error as NSError
        if let code = nsError.userInfo["code"] as? String {
            handleServerError(ReviewRecommendationResponse.ErrorDetail(code: code, message: nsError.localizedDescription))
        } else {
            errorMessage = error.localizedDescription
        }
    }
}
