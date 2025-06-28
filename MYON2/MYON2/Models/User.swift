import Foundation
import FirebaseFirestore

struct User: Codable {
    var name: String?
    var email: String
    var provider: String
    var uid: String
    var createdAt: Date

    enum CodingKeys: String, CodingKey {
        case name
        case email
        case provider
        case uid
        case createdAt = "created_at"
    }
} 