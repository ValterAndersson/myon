import Foundation

/// Routine model for getRoutine API response.
/// Represents a weekly training program with ordered template references.
struct Routine: Codable, Identifiable {
    let id: String
    var name: String
    var description: String?
    var frequency: Int?
    var templateIds: [String]
    var isActive: Bool?
    var lastCompletedTemplateId: String?
    var lastCompletedAt: Date?
    var createdAt: Date?
    var updatedAt: Date?

    enum CodingKeys: String, CodingKey {
        case id, name, description, frequency
        case templateIds = "template_ids"
        case isActive = "is_active"
        case lastCompletedTemplateId = "last_completed_template_id"
        case lastCompletedAt = "last_completed_at"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }

    init(id: String, name: String, description: String? = nil, frequency: Int? = nil,
         templateIds: [String] = [], isActive: Bool? = nil,
         lastCompletedTemplateId: String? = nil, lastCompletedAt: Date? = nil,
         createdAt: Date? = nil, updatedAt: Date? = nil) {
        self.id = id
        self.name = name
        self.description = description
        self.frequency = frequency
        self.templateIds = templateIds
        self.isActive = isActive
        self.lastCompletedTemplateId = lastCompletedTemplateId
        self.lastCompletedAt = lastCompletedAt
        self.createdAt = createdAt
        self.updatedAt = updatedAt
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.id = try container.decodeIfPresent(String.self, forKey: .id) ?? UUID().uuidString
        self.name = try container.decodeIfPresent(String.self, forKey: .name) ?? "Untitled"
        self.description = try container.decodeIfPresent(String.self, forKey: .description)
        self.frequency = try container.decodeIfPresent(Int.self, forKey: .frequency)
        self.templateIds = try container.decodeIfPresent([String].self, forKey: .templateIds) ?? []
        self.isActive = try container.decodeIfPresent(Bool.self, forKey: .isActive)
        self.lastCompletedTemplateId = try container.decodeIfPresent(String.self, forKey: .lastCompletedTemplateId)
        self.lastCompletedAt = try container.decodeIfPresent(Date.self, forKey: .lastCompletedAt)
        self.createdAt = try container.decodeIfPresent(Date.self, forKey: .createdAt)
        self.updatedAt = try container.decodeIfPresent(Date.self, forKey: .updatedAt)
    }
}
