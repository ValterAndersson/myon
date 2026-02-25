import Foundation
import FirebaseFirestore

struct UserAttributes: Codable {
    let id: String?
    var fitnessGoal: String?
    var fitnessLevel: String?
    var equipment: String?
    var height: Double?
    var weight: Double?
    var workoutFrequency: Int?
    var weightFormat: String?
    var heightFormat: String?
    let lastUpdated: Date?

    enum CodingKeys: String, CodingKey {
        case id
        case fitnessGoal = "fitness_goal"
        case fitnessLevel = "fitness_level"
        case equipment = "equipment_preference"
        case height
        case weight
        case workoutFrequency = "workouts_per_week_goal"
        case weightFormat = "weight_format"
        case heightFormat = "height_format"
        case lastUpdated = "last_updated"
    }
    
    // Helper method to merge with location preferences (now removed)
}

struct LinkedDevice: Codable {
    let id: String
    let deviceType: String
    let deviceName: String
    let lastSync: Date
    let isActive: Bool
    let permissions: [String: Bool]
    
    enum CodingKeys: String, CodingKey {
        case id
        case deviceType = "device_type"
        case deviceName = "device_name"
        case lastSync = "last_sync"
        case isActive = "is_active"
        case permissions
    }
} 