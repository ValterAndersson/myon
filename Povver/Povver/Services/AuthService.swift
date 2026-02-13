import Foundation
import FirebaseAuth
import FirebaseFirestore

class AuthService: ObservableObject {
    static let shared = AuthService()
    private let db = Firestore.firestore()
    private var authStateHandle: AuthStateDidChangeListenerHandle?
    
    @Published var isAuthenticated = false
    @Published var currentUser: FirebaseAuth.User?
    
    private init() {
        // Listen for auth state changes
        authStateHandle = Auth.auth().addStateDidChangeListener { [weak self] _, user in
            self?.isAuthenticated = user != nil
            self?.currentUser = user
            
            // Initialize timezone if needed when user signs in
            if let user = user {
                FirebaseConfig.shared.setUserForCrashlytics(user.uid)
                Task {
                    try? await TimezoneManager.shared.initializeTimezoneIfNeeded(userId: user.uid)
                }
            }
        }
    }
    
    func signUp(email: String, password: String) async throws {
        let result = try await Auth.auth().createUser(withEmail: email, password: password)
        let userRef = db.collection("users").document(result.user.uid)
        
        let userData: [String: Any] = [
            "email": email,
            "uid": result.user.uid,
            "created_at": Timestamp(),
            "provider": "email",
            "week_starts_on_monday": true // Default
        ]
        
        try await userRef.setData(userData)
        
        // Initialize timezone if needed
        try await TimezoneManager.shared.initializeTimezoneIfNeeded(userId: result.user.uid)
        
        // Register the current device
        try await DeviceManager.shared.registerCurrentDevice(for: result.user.uid)
    }
    
    func signIn(email: String, password: String) async throws {
        let result = try await Auth.auth().signIn(withEmail: email, password: password)
        
        // Initialize timezone if needed
        try await TimezoneManager.shared.initializeTimezoneIfNeeded(userId: result.user.uid)
        
        // Register/update the current device
        try await DeviceManager.shared.registerCurrentDevice(for: result.user.uid)
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
