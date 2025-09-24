import Foundation

struct ActiveWorkoutDoc: Codable, Identifiable {
    let id: String
    let user_id: String
    let status: String // in_progress | completed | cancelled
    let source_template_id: String?
    let notes: String?
    let plan: Plan?
    let current: Current?
    let exercises: [ExerciseItem]
    let totals: Totals?
    let created_at: Date?
    let start_time: Date?
    let end_time: Date?
    let updated_at: Date?

    struct Plan: Codable {
        let blocks: [Block]
        struct Block: Codable {
            let exercise_id: String
            let sets: [PlanSet]
            let alts: [Alt]?
        }
        struct PlanSet: Codable {
            let target: Target
            struct Target: Codable {
                let reps: Int
                let rir: Int
                let weight: Double?
                let tempo: String?
                let rest_sec: Int?
            }
        }
        struct Alt: Codable { let exercise_id: String; let reason: String? }
    }

    struct Current: Codable {
        let exercise_id: String
        let set_index: Int
        let prescription: Prescription
        struct Prescription: Codable {
            let reps: Int
            let rir_target: Int
            let weight: Double?
            let tempo: String?
            let rest_sec: Int?
        }
    }

    struct ExerciseItem: Codable, Identifiable {
        let id: String
        let exercise_id: String
        let name: String
        let position: Int
        let sets: [ExerciseSet]
    }

    struct ExerciseSet: Codable, Identifiable {
        let id: String
        let reps: Int
        let rir: Int
        let type: String
        let weight: Double
        let is_completed: Bool
    }

    struct Totals: Codable { let sets: Int; let reps: Int; let volume: Double; let stimulus_score: Double }
}

struct ActiveWorkoutEvent: Codable, Identifiable {
    let id: String
    let type: String
    let payload: [String: CodableValue]
    let stimulus: Stimulus?
    let tool_id: String?
    let idempotency_key: String?
    let created_at: Date?

    struct Stimulus: Codable { let score: Double; let rationale: String? }
}

// Helper to decode arbitrary JSON values
enum CodableValue: Codable {
    case string(String)
    case int(Int)
    case double(Double)
    case bool(Bool)
    case array([CodableValue])
    case dictionary([String: CodableValue])
    case null

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() { self = .null; return }
        if let v = try? container.decode(String.self) { self = .string(v); return }
        if let v = try? container.decode(Int.self) { self = .int(v); return }
        if let v = try? container.decode(Double.self) { self = .double(v); return }
        if let v = try? container.decode(Bool.self) { self = .bool(v); return }
        if let v = try? container.decode([String: CodableValue].self) { self = .dictionary(v); return }
        if let v = try? container.decode([CodableValue].self) { self = .array(v); return }
        self = .null
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .string(let v): try container.encode(v)
        case .int(let v): try container.encode(v)
        case .double(let v): try container.encode(v)
        case .bool(let v): try container.encode(v)
        case .array(let v): try container.encode(v)
        case .dictionary(let v): try container.encode(v)
        case .null: try container.encodeNil()
        }
    }
}


