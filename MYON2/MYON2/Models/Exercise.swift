import Foundation

struct Exercise: Identifiable, Codable {
    let id: String
    let name: String
    let category: String
    let metadata: ExerciseMetadata
    let movement: Movement
    let equipment: [String]
    let muscles: Muscles
    let executionNotes: [String]
    let commonMistakes: [String]
    let programmingNotes: [String]
    let stimulusTags: [String]
    let suitabilityNotes: [String]
    
    // Custom init for decoding with defaults for missing optional arrays
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(String.self, forKey: .id)
        name = try container.decode(String.self, forKey: .name)
        category = try container.decode(String.self, forKey: .category)
        metadata = try container.decode(ExerciseMetadata.self, forKey: .metadata)
        movement = try container.decode(Movement.self, forKey: .movement)
        equipment = try container.decodeIfPresent([String].self, forKey: .equipment) ?? []
        muscles = try container.decode(Muscles.self, forKey: .muscles)
        
        // These fields may be missing in some documents - default to empty arrays
        executionNotes = try container.decodeIfPresent([String].self, forKey: .executionNotes) ?? []
        commonMistakes = try container.decodeIfPresent([String].self, forKey: .commonMistakes) ?? []
        programmingNotes = try container.decodeIfPresent([String].self, forKey: .programmingNotes) ?? []
        stimulusTags = try container.decodeIfPresent([String].self, forKey: .stimulusTags) ?? []
        suitabilityNotes = try container.decodeIfPresent([String].self, forKey: .suitabilityNotes) ?? []
    }
    
    // Computed properties for backward compatibility and capitalized text
    var level: String { metadata.level }
    var movementType: String { movement.type }
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
    var capitalizedExecutionNotes: [String] { executionNotes.map { $0.capitalized } }
    var capitalizedCommonMistakes: [String] { commonMistakes.map { $0.capitalized } }
    var capitalizedProgrammingNotes: [String] { programmingNotes.map { $0.capitalized } }
    var capitalizedStimulus: String { stimulus.capitalized }
    var capitalizedSuitability: String { suitability.capitalized }
    
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
        case id
        case name
        case category
        case metadata
        case movement
        case equipment
        case muscles
        case executionNotes = "execution_notes"
        case commonMistakes = "common_mistakes"
        case programmingNotes = "programming_use_cases"
        case stimulusTags = "stimulus_tags"
        case suitabilityNotes = "suitability_notes"
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
    
    enum CodingKeys: String, CodingKey {
        case level
        case planeOfMotion = "plane_of_motion"
        case unilateral
    }
}

struct Movement: Codable {
    let split: String?
    let type: String
}

struct Muscles: Codable {
    let category: [String]?
    let primary: [String]
    let secondary: [String]
    let contribution: [String: Double]?
    
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        category = try container.decodeIfPresent([String].self, forKey: .category)
        primary = try container.decodeIfPresent([String].self, forKey: .primary) ?? []
        secondary = try container.decodeIfPresent([String].self, forKey: .secondary) ?? []
        contribution = try container.decodeIfPresent([String: Double].self, forKey: .contribution)
    }
}
