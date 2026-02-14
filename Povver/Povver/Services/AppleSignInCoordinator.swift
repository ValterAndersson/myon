import AuthenticationServices
import CryptoKit
import Foundation

/// Wraps ASAuthorizationController's delegate pattern into async/await.
/// Returns the Apple ID credential along with the raw nonce needed for Firebase.
@MainActor
class AppleSignInCoordinator: NSObject, ASAuthorizationControllerDelegate,
    ASAuthorizationControllerPresentationContextProviding
{
    private var continuation: CheckedContinuation<AppleSignInResult, Error>?
    private var currentNonce: String?

    struct AppleSignInResult {
        let idToken: String
        let rawNonce: String
        let authorizationCode: String?
        let fullName: PersonNameComponents?
        let email: String?
    }

    /// Presents the Apple Sign-In sheet and returns the result.
    ///
    /// SECURITY: sha256(nonce) is sent to Apple for anti-replay validation.
    /// The raw nonce is kept locally and passed to Firebase, which verifies
    /// it against Apple's hashed version. This prevents credential replay attacks.
    func signIn() async throws -> AppleSignInResult {
        let nonce = randomNonceString()
        currentNonce = nonce

        let provider = ASAuthorizationAppleIDProvider()
        let request = provider.createRequest()
        request.requestedScopes = [.fullName, .email]
        request.nonce = sha256(nonce)

        let controller = ASAuthorizationController(authorizationRequests: [request])
        controller.delegate = self
        controller.presentationContextProvider = self
        controller.performRequests()

        // Bridge ASAuthorizationController's delegate callbacks to async/await.
        // Continuation is resumed in authorizationController delegate methods below.
        return try await withCheckedThrowingContinuation { continuation in
            self.continuation = continuation
        }
    }

    // MARK: - ASAuthorizationControllerDelegate

    func authorizationController(
        controller: ASAuthorizationController,
        didCompleteWithAuthorization authorization: ASAuthorization
    ) {
        guard let credential = authorization.credential as? ASAuthorizationAppleIDCredential,
              let idTokenData = credential.identityToken,
              let idToken = String(data: idTokenData, encoding: .utf8),
              let nonce = currentNonce
        else {
            continuation?.resume(throwing: AppleSignInError.missingCredential)
            continuation = nil
            return
        }

        let authCode: String?
        if let codeData = credential.authorizationCode {
            authCode = String(data: codeData, encoding: .utf8)
        } else {
            authCode = nil
        }

        let result = AppleSignInResult(
            idToken: idToken,
            rawNonce: nonce,
            authorizationCode: authCode,
            fullName: credential.fullName,
            email: credential.email
        )
        continuation?.resume(returning: result)
        continuation = nil
    }

    func authorizationController(
        controller: ASAuthorizationController,
        didCompleteWithError error: Error
    ) {
        continuation?.resume(throwing: error)
        continuation = nil
    }

    // MARK: - ASAuthorizationControllerPresentationContextProviding

    func presentationAnchor(for controller: ASAuthorizationController) -> ASPresentationAnchor {
        UIApplication.shared.connectedScenes
            .compactMap { $0 as? UIWindowScene }
            .flatMap { $0.windows }
            .first { $0.isKeyWindow } ?? ASPresentationAnchor()
    }

    // MARK: - Nonce Helpers

    /// Generates a random nonce string for Apple Sign-In security.
    private func randomNonceString(length: Int = 32) -> String {
        precondition(length > 0)
        var randomBytes = [UInt8](repeating: 0, count: length)
        let errorCode = SecRandomCopyBytes(kSecRandomDefault, randomBytes.count, &randomBytes)
        if errorCode != errSecSuccess {
            fatalError("Unable to generate nonce. SecRandomCopyBytes failed with OSStatus \(errorCode)")
        }
        let charset: [Character] = Array("0123456789ABCDEFGHIJKLMNOPQRSTUVXYZabcdefghijklmnopqrstuvwxyz-._")
        return String(randomBytes.map { charset[Int($0) % charset.count] })
    }

    /// SHA256 hash of the nonce, sent to Apple. Firebase verifies the raw nonce against this.
    private func sha256(_ input: String) -> String {
        let inputData = Data(input.utf8)
        let hashedData = SHA256.hash(data: inputData)
        return hashedData.compactMap { String(format: "%02x", $0) }.joined()
    }
}

enum AppleSignInError: LocalizedError {
    case missingCredential

    var errorDescription: String? {
        "Apple Sign-In failed. Please try again."
    }
}
