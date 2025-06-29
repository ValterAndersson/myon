import Foundation
import FirebaseFirestore

class UserRepository {
    private let db = Firestore.firestore()
    private let collection = "users"
    
    func getUser(userId: String) async throws -> User? {
        do {
            let doc = try await db.collection(collection).document(userId).getDocument()
            if doc.exists {
                let user = try doc.data(as: User.self)
                return user
            } else {
                return nil
            }
        } catch {
            print("[UserRepository] getUser error for userId \(userId): \(error)")
            throw error
        }
    }
    
    func updateUser(userId: String, user: User) async throws {
        do {
            try await db.collection(collection).document(userId).setData(from: user, merge: true)
        } catch {
            print("[UserRepository] updateUser error for userId \(userId): \(error)")
            throw error
        }
    }
    
    // MARK: - User Profile
    
    func updateUserProfile(userId: String, name: String, email: String, weekStartsOnMonday: Bool? = nil, timeZone: String? = nil) async throws {
        let userRef = db.collection(collection).document(userId)
        var updates: [String: Any] = [
            "name": name,
            "email": email,
            "updated_at": FieldValue.serverTimestamp()
        ]
        if let weekStartsOnMonday = weekStartsOnMonday {
            updates["week_starts_on_monday"] = weekStartsOnMonday
        }
        if let timeZone = timeZone {
            updates["timezone"] = timeZone
        }
        try await userRef.updateData(updates)
    }
    
    func deleteUser(userId: String) async throws {
        let userRef = db.collection(collection).document(userId)
        
        // Delete all subcollections first
        let subcollections = ["user_attributes", "linked_devices", "workouts", "workout_templates"]
        for subcollection in subcollections {
            let snapshot = try await userRef.collection(subcollection).getDocuments()
            for document in snapshot.documents {
                try await document.reference.delete()
            }
        }
        
        // Finally delete the user document
        try await userRef.delete()
    }
    
    // MARK: - User Attributes
    
    func saveUserAttributes(_ attributes: UserAttributes) async throws {
        guard let id = attributes.id else {
            throw NSError(domain: "UserRepository", code: 0, userInfo: [NSLocalizedDescriptionKey: "UserAttributes.id is nil"])
        }
        let userRef = db.collection("users").document(id)
        let attributesRef = userRef.collection("user_attributes").document(id)
        try await attributesRef.setData(from: attributes)
    }
    
    func getUserAttributes(userId: String) async throws -> UserAttributes? {
        let userRef = db.collection("users").document(userId)
        let attributesRef = userRef.collection("user_attributes").document(userId)
        let document = try await attributesRef.getDocument()
        
        if document.exists {
            return try document.data(as: UserAttributes.self)
        } else {
            return nil
        }
    }
    
    // MARK: - Linked Devices
    
    func addLinkedDevice(_ device: LinkedDevice, userId: String) async throws {
        let userRef = db.collection("users").document(userId)
        let devicesRef = userRef.collection("linked_devices").document(device.id)
        try await devicesRef.setData(from: device)
    }
    
    func removeLinkedDevice(deviceId: String, userId: String) async throws {
        let userRef = db.collection("users").document(userId)
        let deviceRef = userRef.collection("linked_devices").document(deviceId)
        try await deviceRef.delete()
    }
    
    func getLinkedDevices(userId: String) async throws -> [LinkedDevice] {
        let userRef = db.collection("users").document(userId)
        let devicesRef = userRef.collection("linked_devices")
        let snapshot = try await devicesRef.getDocuments()
        return try snapshot.documents.compactMap { try $0.data(as: LinkedDevice.self) }
    }
    
    func updateDeviceSync(deviceId: String, userId: String) async throws {
        let userRef = db.collection("users").document(userId)
        let deviceRef = userRef.collection("linked_devices").document(deviceId)
        try await deviceRef.updateData([
            "last_sync": FieldValue.serverTimestamp(),
            "is_active": true
        ])
    }
    
    // MARK: - User Preferences
    
    func updateUserPreferences(userId: String, timezone: String? = nil, locale: String? = nil, currency: String? = nil) async throws {
        let userRef = db.collection("users").document(userId)
        let attributesRef = userRef.collection("user_attributes").document(userId)
        
        var updates: [String: Any] = [:]
        if let timezone = timezone { updates["timezone"] = timezone }
        if let locale = locale { updates["locale"] = locale }
        if let currency = currency { updates["currency"] = currency }
        updates["last_updated"] = FieldValue.serverTimestamp()
        
        try await attributesRef.updateData(updates)
    }
} 
