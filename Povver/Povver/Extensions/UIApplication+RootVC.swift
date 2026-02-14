import UIKit

extension UIApplication {
    /// Returns the root view controller of the key window.
    /// Used by GoogleSignIn SDK which requires a presenting view controller.
    var rootViewController: UIViewController? {
        connectedScenes
            .compactMap { $0 as? UIWindowScene }
            .flatMap { $0.windows }
            .first { $0.isKeyWindow }?
            .rootViewController
    }
}
