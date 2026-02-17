import Foundation
import FirebaseFirestore

struct AgentRecommendation: Identifiable, Codable {
    @DocumentID var id: String?
    let createdAt: Date
    let trigger: String
    let scope: String
    let target: RecommendationTarget
    let recommendation: RecommendationDetail
    var state: String
    let appliedBy: String?
    let appliedAt: Date?
    let result: [String: AnyCodable]?

    enum CodingKeys: String, CodingKey {
        case id
        case createdAt = "created_at"
        case trigger
        case scope
        case target
        case recommendation
        case state
        case appliedBy = "applied_by"
        case appliedAt = "applied_at"
        case result
    }

    // Resilient decoding: serverTimestamp() can be null/pending on first local snapshot.
    // Non-optional fields use decodeIfPresent + sensible defaults to prevent silent drops.
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        _id = try container.decode(DocumentID<String>.self, forKey: .id)
        createdAt = try container.decodeIfPresent(Date.self, forKey: .createdAt) ?? Date()
        trigger = try container.decodeIfPresent(String.self, forKey: .trigger) ?? "unknown"
        scope = try container.decodeIfPresent(String.self, forKey: .scope) ?? "template"
        target = try container.decodeIfPresent(RecommendationTarget.self, forKey: .target) ?? RecommendationTarget()
        recommendation = try container.decodeIfPresent(RecommendationDetail.self, forKey: .recommendation) ?? RecommendationDetail()
        state = try container.decodeIfPresent(String.self, forKey: .state) ?? "pending_review"
        appliedBy = try container.decodeIfPresent(String.self, forKey: .appliedBy)
        appliedAt = try container.decodeIfPresent(Date.self, forKey: .appliedAt)
        result = try container.decodeIfPresent([String: AnyCodable].self, forKey: .result)
    }
}

struct RecommendationTarget: Codable {
    let templateId: String?
    let routineId: String?
    let exerciseName: String?
    let exerciseId: String?
    let templateName: String?

    enum CodingKeys: String, CodingKey {
        case templateId = "template_id"
        case routineId = "routine_id"
        case exerciseName = "exercise_name"
        case exerciseId = "exercise_id"
        case templateName = "template_name"
    }

    init(templateId: String? = nil, routineId: String? = nil, exerciseName: String? = nil, exerciseId: String? = nil, templateName: String? = nil) {
        self.templateId = templateId
        self.routineId = routineId
        self.exerciseName = exerciseName
        self.exerciseId = exerciseId
        self.templateName = templateName
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        templateId = try container.decodeIfPresent(String.self, forKey: .templateId)
        routineId = try container.decodeIfPresent(String.self, forKey: .routineId)
        exerciseName = try container.decodeIfPresent(String.self, forKey: .exerciseName)
        exerciseId = try container.decodeIfPresent(String.self, forKey: .exerciseId)
        templateName = try container.decodeIfPresent(String.self, forKey: .templateName)
    }
}

struct RecommendationDetail: Codable {
    let type: String
    let changes: [RecommendationChange]
    let summary: String
    let rationale: String?
    let confidence: Double
    let signals: [String]

    init(type: String = "unknown", changes: [RecommendationChange] = [], summary: String = "", rationale: String? = nil, confidence: Double = 0, signals: [String] = []) {
        self.type = type
        self.changes = changes
        self.summary = summary
        self.rationale = rationale
        self.confidence = confidence
        self.signals = signals
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        type = try container.decodeIfPresent(String.self, forKey: .type) ?? "unknown"
        changes = try container.decodeIfPresent([RecommendationChange].self, forKey: .changes) ?? []
        summary = try container.decodeIfPresent(String.self, forKey: .summary) ?? ""
        rationale = try container.decodeIfPresent(String.self, forKey: .rationale)
        confidence = try container.decodeIfPresent(Double.self, forKey: .confidence) ?? 0
        signals = try container.decodeIfPresent([String].self, forKey: .signals) ?? []
    }
}

struct RecommendationChange: Codable {
    let path: String
    let from: AnyCodable
    let to: AnyCodable
    let rationale: String?

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        path = try container.decodeIfPresent(String.self, forKey: .path) ?? ""
        from = try container.decodeIfPresent(AnyCodable.self, forKey: .from) ?? AnyCodable(NSNull())
        to = try container.decodeIfPresent(AnyCodable.self, forKey: .to) ?? AnyCodable(NSNull())
        rationale = try container.decodeIfPresent(String.self, forKey: .rationale)
    }
}
