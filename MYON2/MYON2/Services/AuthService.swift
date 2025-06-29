import Foundation
import FirebaseAuth
import FirebaseFirestore

class AuthService: ObservableObject {
    static let shared = AuthService()
    private let db = Firestore.firestore()
    
    @Published var isAuthenticated = false
    @Published var currentUser: FirebaseAuth.User?
    
    private init() {
        // Listen for auth state changes
        Auth.auth().addStateDidChangeListener { [weak self] _, user in
            self?.isAuthenticated = user != nil
            self?.currentUser = user
        }
    }
    
    func signUp(email: String, password: String) async throws {
        let result = try await Auth.auth().createUser(withEmail: email, password: password)
        let userRef = db.collection("users").document(result.user.uid)
        
        // Get current device timezone
        let currentTimeZone = TimeZone.current.identifier
        
        let userData: [String: Any] = [
            "email": email,
            "uid": result.user.uid,
            "created_at": Timestamp(),
            "provider": "email",
            "timezone": currentTimeZone,
            "week_starts_on_monday": true // Default
        ]
        
        try await userRef.setData(userData)
        
        // Register the current device
        try await DeviceManager.shared.registerCurrentDevice(for: result.user.uid)
    }
    
    func signIn(email: String, password: String) async throws {
        let result = try await Auth.auth().signIn(withEmail: email, password: password)
        
        // Register/update the current device
        try await DeviceManager.shared.registerCurrentDevice(for: result.user.uid)
        // No location, locale, or currency logic needed
    }
    
    // Placeholder for Google sign-in
    func signInWithGoogle() async throws {
        // TODO: Implement Google sign-in
    }
    
    // Placeholder for Apple sign-in
    func signInWithApple() async throws {
        // TODO: Implement Apple sign-in
    }
    
    func signOut() throws {
        try Auth.auth().signOut()
    }
} 