import Foundation
import FirebaseCore
import FirebaseFirestore
import FirebaseCrashlytics
import FirebaseAnalytics

class FirebaseConfig {
    static let shared = FirebaseConfig()

    private init() {}

    func configure() {
        FirebaseApp.configure()

        // Crashlytics is auto-initialized by Firebase once the SDK is linked.
        // Set user ID once auth is available so crash reports are attributable.
        Crashlytics.crashlytics().setCrashlyticsCollectionEnabled(true)
    }

    /// Call after authentication to tag crash reports with the current user.
    func setUserForCrashlytics(_ userId: String) {
        Crashlytics.crashlytics().setUserID(userId)
    }

    /// Call after authentication to set user ID for analytics attribution.
    func setUserForAnalytics(_ userId: String) {
        Analytics.setUserID(userId)
    }

    /// Log non-fatal errors to Crashlytics for field diagnostics.
    func recordError(_ error: Error, context: [String: String] = [:]) {
        let crashlytics = Crashlytics.crashlytics()
        for (key, value) in context {
            crashlytics.setCustomValue(value, forKey: key)
        }
        crashlytics.record(error: error)
    }

    /// Log breadcrumb messages visible in crash report timelines.
    func log(_ message: String) {
        Crashlytics.crashlytics().log(message)
    }

    // MARK: - Firestore References

    var db: Firestore {
        return Firestore.firestore()
    }

    // MARK: - Collection References

    var usersCollection: CollectionReference {
        return db.collection("users")
    }

    var workoutsCollection: CollectionReference {
        return db.collection("workouts")
    }

    var exercisesCollection: CollectionReference {
        return db.collection("exercises")
    }
}
