import Foundation
import FirebaseFirestore

struct Exercise: Identifiable, Codable {
    @DocumentID var id: String?
    let name: String
    let category: String
    let description: String
    let metadata: ExerciseMetadata
    let movement: Movement
    let equipment: [String]
    let muscles: Muscles
    let executionNotes: [String]
    let commonMistakes: [String]
    let programmingNotes: [String]
    let stimulusTags: [String]
    let suitabilityNotes: [String]
    let coachingCues: [String]
    let tips: [String]
    let status: String

    // Custom init for decoding with defaults for missing optional fields
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        // Initialize @DocumentID wrapper - Firestore will inject the actual doc ID after decoding
        _id = DocumentID(wrappedValue: nil)
        name = try container.decodeIfPresent(String.self, forKey: .name) ?? "Unknown Exercise"
        category = try container.decodeIfPresent(String.self, forKey: .category) ?? "exercise"
        description = try container.decodeIfPresent(String.self, forKey: .description) ?? ""
        metadata = try container.decodeIfPresent(ExerciseMetadata.self, forKey: .metadata) ?? ExerciseMetadata.empty
        movement = try container.decodeIfPresent(Movement.self, forKey: .movement) ?? Movement.empty
        equipment = try container.decodeIfPresent([String].self, forKey: .equipment) ?? []
        muscles = try container.decodeIfPresent(Muscles.self, forKey: .muscles) ?? Muscles.empty

        // Content arrays - default to empty if missing
        executionNotes = try container.decodeIfPresent([String].self, forKey: .executionNotes) ?? []
        commonMistakes = try container.decodeIfPresent([String].self, forKey: .commonMistakes) ?? []
        programmingNotes = try container.decodeIfPresent([String].self, forKey: .programmingNotes) ?? []
        stimulusTags = try container.decodeIfPresent([String].self, forKey: .stimulusTags) ?? []
        suitabilityNotes = try container.decodeIfPresent([String].self, forKey: .suitabilityNotes) ?? []
        coachingCues = try container.decodeIfPresent([String].self, forKey: .coachingCues) ?? []
        tips = try container.decodeIfPresent([String].self, forKey: .tips) ?? []
        status = try container.decodeIfPresent(String.self, forKey: .status) ?? "approved"
    }
    
    // Computed properties for backward compatibility and capitalized text
    var level: String { metadata.level }
    var movementType: String { movement.type }
    var movementSplit: String? { movement.split }
    var primaryMuscles: [String] { muscles.primary }
    var secondaryMuscles: [String] { muscles.secondary }
    var muscleCategories: [String] { muscles.category ?? [] }
    var muscleContributions: [String: Double] { muscles.contribution ?? [:] }
    var stimulus: String { stimulusTags.joined(separator: ", ") }
    var suitability: String { suitabilityNotes.joined(separator: " ") }

    var capitalizedName: String { name.capitalized }
    var capitalizedCategory: String { category.capitalized }
    var capitalizedLevel: String { level.capitalized }
    var capitalizedMovementType: String { movementType.capitalized }
    var capitalizedMovementSplit: String? { movementSplit?.capitalized }
    var capitalizedEquipment: String { equipment.joined(separator: ", ").capitalized }
    var capitalizedPrimaryMuscles: [String] { primaryMuscles.map { $0.capitalized } }
    var capitalizedSecondaryMuscles: [String] { secondaryMuscles.map { $0.capitalized } }
    var capitalizedMuscleCategories: [String] {
        guard let categories = muscles.category else { return [] }
        return categories.map { $0.capitalized }
    }
    var capitalizedMuscleContributions: [String: Double] {
        guard let contributions = muscles.contribution else { return [:] }
        return Dictionary(uniqueKeysWithValues: contributions.map { ($0.key.capitalized, $0.value) })
    }
    var capitalizedExecutionNotes: [String] { executionNotes }  // Don't capitalize sentences
    var capitalizedCommonMistakes: [String] { commonMistakes }
    var capitalizedProgrammingNotes: [String] { programmingNotes }
    var capitalizedCoachingCues: [String] { coachingCues }
    var capitalizedTips: [String] { tips }
    var capitalizedStimulus: String { stimulus }
    var capitalizedSuitability: String { suitability }
    
    // Convenience methods for muscle contributions
    func getContribution(for muscle: String) -> Double? {
        return muscleContributions[muscle]
    }
    
    func getTopContributingMuscles(limit: Int = 3) -> [(muscle: String, contribution: Double)] {
        return muscleContributions
            .sorted { $0.value > $1.value }
            .prefix(limit)
            .map { (muscle: $0.key, contribution: $0.value) }
    }
    
    func getContributionPercentage(for muscle: String) -> String {
        guard let contribution = getContribution(for: muscle) else { return "0%" }
        return String(format: "%.0f%%", contribution * 100)
    }
    
    enum CodingKeys: String, CodingKey {
        // Note: id is NOT included here - @DocumentID is injected by Firestore from document path
        case name
        case category
        case description
        case metadata
        case movement
        case equipment
        case muscles
        case executionNotes = "execution_notes"
        case commonMistakes = "common_mistakes"
        case programmingNotes = "programming_use_cases"
        case stimulusTags = "stimulus_tags"
        case suitabilityNotes = "suitability_notes"
        case coachingCues = "coaching_cues"
        case tips
        case status
    }
}

struct ExerciseImages: Codable {
    let relaxedUrl: String
    let tensionUrl: String
    
    enum CodingKeys: String, CodingKey {
        case relaxedUrl = "relaxed_url"
        case tensionUrl = "tension_url"
    }
}

struct ExerciseMetadata: Codable {
    let level: String
    let planeOfMotion: String?
    let unilateral: Bool?

    static let empty = ExerciseMetadata(level: "intermediate", planeOfMotion: nil, unilateral: nil)

    init(level: String, planeOfMotion: String?, unilateral: Bool?) {
        self.level = level
        self.planeOfMotion = planeOfMotion
        self.unilateral = unilateral
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        level = try container.decodeIfPresent(String.self, forKey: .level) ?? "intermediate"
        // Handle both string and array formats for plane_of_motion
        if let stringValue = try? container.decodeIfPresent(String.self, forKey: .planeOfMotion) {
            planeOfMotion = stringValue
        } else if let arrayValue = try? container.decodeIfPresent([String].self, forKey: .planeOfMotion) {
            planeOfMotion = arrayValue.first
        } else {
            planeOfMotion = nil
        }
        unilateral = try container.decodeIfPresent(Bool.self, forKey: .unilateral)
    }

    enum CodingKeys: String, CodingKey {
        case level
        case planeOfMotion = "plane_of_motion"
        case unilateral
    }
}

struct Movement: Codable {
    let split: String?
    let type: String

    static let empty = Movement(split: nil, type: "other")

    init(split: String?, type: String) {
        self.split = split
        self.type = type
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        // Handle both string and array formats for split
        if let stringValue = try? container.decodeIfPresent(String.self, forKey: .split) {
            split = stringValue
        } else if let arrayValue = try? container.decodeIfPresent([String].self, forKey: .split) {
            split = arrayValue.first
        } else {
            split = nil
        }
        type = try container.decodeIfPresent(String.self, forKey: .type) ?? "other"
    }

    enum CodingKeys: String, CodingKey {
        case split
        case type
    }
}

struct Muscles: Codable {
    let category: [String]?
    let primary: [String]
    let secondary: [String]
    let contribution: [String: Double]?
    
    static let empty = Muscles(category: nil, primary: [], secondary: [], contribution: nil)
    
    init(category: [String]?, primary: [String], secondary: [String], contribution: [String: Double]?) {
        self.category = category
        self.primary = primary
        self.secondary = secondary
        self.contribution = contribution
    }
    
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        category = try container.decodeIfPresent([String].self, forKey: .category)
        primary = try container.decodeIfPresent([String].self, forKey: .primary) ?? []
        secondary = try container.decodeIfPresent([String].self, forKey: .secondary) ?? []
        contribution = try container.decodeIfPresent([String: Double].self, forKey: .contribution)
    }
}
