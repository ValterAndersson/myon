import Foundation
import FirebaseFirestore

struct User: Codable {
    var name: String?
    var email: String
    var provider: String
    var uid: String
    var createdAt: Date
    var weekStartsOnMonday: Bool = true  // Default to Monday

    enum CodingKeys: String, CodingKey {
        case name
        case email
        case provider
        case uid
        case createdAt = "created_at"
        case weekStartsOnMonday = "week_starts_on_monday"
    }
} 