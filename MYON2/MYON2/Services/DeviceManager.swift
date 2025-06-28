import Foundation
import UIKit
import FirebaseFirestore

class DeviceManager {
    static let shared = DeviceManager()
    private let db = Firestore.firestore()
    
    private init() {}
    
    var currentDeviceId: String {
        // Use the device's identifierForVendor as a unique identifier
        UIDevice.current.identifierForVendor?.uuidString ?? UUID().uuidString
    }
    
    var deviceInfo: [String: Any] {
        [
            "id": currentDeviceId,
            "type": UIDevice.current.model,
            "name": UIDevice.current.name,
            "system_name": UIDevice.current.systemName,
            "system_version": UIDevice.current.systemVersion,
            "last_sync": FieldValue.serverTimestamp(),
            "is_active": true
        ]
    }
    
    func registerCurrentDevice(for userId: String) async throws {
        let userRef = db.collection("users").document(userId)
        let deviceRef = userRef.collection("linked_devices").document(currentDeviceId)
        
        // Check if device already exists
        let document = try await deviceRef.getDocument()
        if !document.exists {
            // Only create if it doesn't exist
            try await deviceRef.setData(deviceInfo)
        } else {
            // Update last sync and active status
            try await deviceRef.updateData([
                "last_sync": FieldValue.serverTimestamp(),
                "is_active": true
            ])
        }
    }
    
    func updateDeviceSync(for userId: String) async throws {
        let userRef = db.collection("users").document(userId)
        let deviceRef = userRef.collection("linked_devices").document(currentDeviceId)
        
        try await deviceRef.updateData([
            "last_sync": FieldValue.serverTimestamp(),
            "is_active": true
        ])
    }
} 