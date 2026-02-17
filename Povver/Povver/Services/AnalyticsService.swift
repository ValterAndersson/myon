import Foundation
import FirebaseAnalytics

/// Thin wrapper around Firebase Analytics providing typed event methods.
/// Milestone events (first_message_sent, etc.) fire once per install via UserDefaults guard.
final class AnalyticsService {
    static let shared = AnalyticsService()
    private init() {}

    // MARK: - User Identity

    func setUserId(_ userId: String) {
        Analytics.setUserID(userId)
    }

    // MARK: - App Lifecycle

    func appOpened() {
        log("app_opened")
    }

    func signupCompleted(provider: String) {
        log("signup_completed", params: ["provider": provider])
    }

    // MARK: - Conversation

    func conversationStarted(entryPoint: String) {
        log("conversation_started", params: ["entry_point": entryPoint])
    }

    func messageSent(messageLength: Int) {
        log("message_sent", params: ["message_length": messageLength])
        logOnce("first_message_sent")
    }

    // MARK: - Artifacts

    func artifactReceived(artifactType: String) {
        log("artifact_received", params: ["artifact_type": artifactType])
        logOnce("first_artifact_received")
    }

    func artifactAction(action: String, artifactType: String) {
        log("artifact_action", params: ["action": action, "artifact_type": artifactType])
    }

    // MARK: - Workouts

    func workoutStarted(source: String) {
        log("workout_started", params: ["source": source])
    }

    func workoutCompleted(durationMin: Int, exerciseCount: Int, setCount: Int) {
        log("workout_completed", params: [
            "duration_min": durationMin,
            "exercise_count": exerciseCount,
            "set_count": setCount,
        ])
        logOnce("first_workout_completed")
    }

    func workoutCancelled(durationMin: Int) {
        log("workout_cancelled", params: ["duration_min": durationMin])
    }

    func workoutCoachOpened() {
        log("workout_coach_opened")
    }

    // MARK: - Monetization

    func paywallShown(trigger: String) {
        log("paywall_shown", params: ["trigger": trigger])
    }

    func trialStarted() {
        log("trial_started")
    }

    func subscriptionPurchased(productId: String) {
        log("subscription_purchased", params: ["product_id": productId])
    }

    // MARK: - Recommendations

    func recommendationShown(type: String, scope: String) {
        log("recommendation_shown", params: ["type": type, "scope": scope])
    }

    func recommendationAction(action: String, type: String) {
        log("recommendation_action", params: ["action": action, "type": type])
    }

    // MARK: - Errors

    func streamingError(errorCode: String) {
        log("streaming_error", params: ["error_code": errorCode])
    }

    // MARK: - Private

    private func log(_ name: String, params: [String: Any]? = nil) {
        Analytics.logEvent(name, parameters: params)
        #if DEBUG
        if let params = params {
            print("[Analytics] \(name): \(params)")
        } else {
            print("[Analytics] \(name)")
        }
        #endif
    }

    /// Fire a milestone event exactly once per app install.
    private func logOnce(_ name: String) {
        let key = "analytics_milestone_\(name)"
        guard !UserDefaults.standard.bool(forKey: key) else { return }
        UserDefaults.standard.set(true, forKey: key)
        log(name)
    }
}
