import Foundation
import FirebaseFirestore

// MARK: - DTOs matching platformvision.md

public enum CanvasPhase: String, Codable { case planning, active, analysis }

public struct CanvasStateDTO: Codable {
    public let phase: CanvasPhase?
    public let version: Int?
    public let purpose: String?
    public let lanes: [String]?
}

public struct UpNextEntryDTO: Codable {
    public let card_id: String
    public let priority: Int
    public let inserted_at: Date?
}

public struct CanvasActionDTO: Codable {
    public let type: String
    public let card_id: String?
    public let payload: [String: AnyCodable]?
    public let by: String?
    public let idempotency_key: String
}

public struct ApplyActionRequestDTO: Codable {
    public let canvasId: String
    public let expected_version: Int?
    public let action: CanvasActionDTO
}

public struct ChangedCardDTO: Codable { public let card_id: String; public let status: String }

public struct ApplyActionResponseDTO: Codable {
    public struct DataDTO: Codable {
        public let state: CanvasStateDTO?
        public let changed_cards: [ChangedCardDTO]?
        public let up_next_delta: [AnyCodable]?
        public let version: Int?
    }
    public let success: Bool
    public let data: DataDTO?
    public let error: ActionErrorDTO?
}

public struct ActionErrorDTO: Codable { public let code: String; public let message: String; public let details: [String: AnyCodable]? }

// MARK: - Aggregated Snapshot for UI

public struct CanvasSnapshot {
    public let version: Int
    public let state: CanvasStateDTO
    public let cards: [CanvasCardModel]
    public let upNext: [String]
}

// MARK: - Firestore Mappers

public enum CanvasMapper {
    public static func mapCard(from doc: DocumentSnapshot) -> CanvasCardModel? {
        let data = doc.data() ?? [:]
        guard let statusStr = data["status"] as? String else { return nil }
        let rawType = (data["type"] as? String) ?? "summary"
        let laneStr = (data["lane"] as? String) ?? "analysis"
        let title = data["title"] as? String
        let subtitle = data["subtitle"] as? String
        let status = CardStatus(rawValue: statusStr) ?? .active
        let lane = CardLane(rawValue: laneStr) ?? .analysis

        // Shared fields
        var width: CardWidth = .oneHalf
        if let w = (data["layout"] as? [String: Any])?["width"] as? String { width = CardWidth(rawValue: w) ?? width }
        else if let w = data["width"] as? String { width = CardWidth(rawValue: w) ?? width }

        let actions = parseActions(array: data["actions"]) ?? []
        let menuItems = parseActions(array: data["menuItems"]) ?? []
        let meta: CardMeta? = {
            guard let m = data["meta"] as? [String: Any] else { return nil }
            let context = m["context"] as? String
            let groupId = m["groupId"] as? String ?? m["group_id"] as? String
            let pinned = m["pinned"] as? Bool
            let dismissible = m["dismissible"] as? Bool
            return CardMeta(context: context, groupId: groupId, pinned: pinned, dismissible: dismissible)
        }()

        // Content mapping (tolerant to evolving backend types)
        let content = data["content"] as? [String: Any]
        let modelData: CanvasCardData = {
            switch rawType {
            case "visualization":
                let t = (content?["chart_type"] as? String) ?? "chart"
                return .visualization(title: t.capitalized, subtitle: nil)
            case "session_plan":
                let blocks = (content?["blocks"] as? [[String: Any]]) ?? []
                let exercises: [PlanExercise] = blocks.compactMap { blk in
                    let exName = (blk["name"] as? String) ?? (blk["exercise_name"] as? String)
                    let exId = blk["exercise_id"] as? String
                    var setCount = 0
                    if let setsArr = blk["sets"] as? [[String: Any]] {
                        setCount = setsArr.count
                    } else if let setsInt = blk["sets"] as? Int {
                        setCount = setsInt
                    } else if let setCountValue = blk["set_count"] as? Int {
                        setCount = setCountValue
                    }
                    let label = exName ?? exId
                    guard let name = label else { return nil }
                    return PlanExercise(id: exId ?? UUID().uuidString, name: name, sets: max(setCount, 1))
                }
                return .sessionPlan(exercises: exercises)
            case "proposal-group":
                return .groupHeader(title: title ?? (content?["title"] as? String ?? ""))
            case "inline-info":
                let text = (content?["text"] as? String) ?? (content?["summary"] as? String) ?? "Info"
                return .inlineInfo(text)
            case "clarify-questions":
                let qsArray = (content?["questions"] as? [[String: Any]]) ?? []
                let qs: [ClarifyQuestion] = qsArray.compactMap { q in
                    // Support both 'text' and 'label' fields for backwards compatibility
                    guard let text = (q["text"] as? String) ?? (q["label"] as? String) else { return nil }
                    let typeStr = (q["type"] as? String) ?? "text"
                    let qType = ClarifyQuestionType(rawValue: typeStr) ?? .text
                    let opts = q["options"] as? [String]
                    let qId = (q["id"] as? String) ?? UUID().uuidString
                    return ClarifyQuestion(id: qId, text: text, options: opts, type: qType)
                }
                return .clarifyQuestions(qs)
            case "routine-overview":
                let split = (content?["split"] as? String) ?? ""
                let days = (content?["days"] as? Int) ?? 0
                let notes = content?["notes"] as? String
                return .routineOverview(split: split, days: days, notes: notes)
            case "agent-message":
                let type = content?["type"] as? String
                let status = content?["status"] as? String
                let message = content?["message"] as? String
                let thoughts = content?["thoughts"] as? [String]
                
                var toolCalls: [ToolCall]? = nil
                if let tools = content?["toolCalls"] as? [[String: Any]] {
                    toolCalls = tools.map { tool in
                        ToolCall(
                            id: (tool["id"] as? String) ?? UUID().uuidString,
                            name: (tool["name"] as? String) ?? "",
                            displayName: (tool["displayName"] as? String) ?? (tool["name"] as? String) ?? "",
                            duration: tool["duration"] as? String
                        )
                    }
                }
                
                return .agentMessage(AgentMessage(
                    type: type,
                    status: status,
                    message: message,
                    toolCalls: toolCalls,
                    thoughts: thoughts
                ))
            case "list":
                let items = (content?["items"] as? [[String: Any]]) ?? []
                let options: [ListOption] = items.map { item in
                    ListOption(title: (item["title"] as? String) ?? "Item",
                               subtitle: item["subtitle"] as? String,
                               iconSystemName: item["iconSystemName"] as? String)
                }
                return .list(options: options)
            case "analysis_task":
                if let steps = (content?["steps"] as? [[String: Any]]) {
                    let parsed: [AgentStreamStep] = steps.map { s in
                        let kindStr = (s["kind"] as? String) ?? (s["type"] as? String) ?? "info"
                        let kind = AgentStreamStep.Kind(rawValue: kindStr) ?? .info
                        return AgentStreamStep(kind: kind, text: s["text"] as? String, durationMs: s["durationMs"] as? Int)
                    }
                    return .agentStream(steps: parsed)
                }
                fallthrough
            default:
                let text = (content?["text"] as? String) ?? (content?["summary"] as? String) ?? rawType.capitalized
                return .text(text)
            }
        }()

        let cardType = CardType(rawValue: rawType) ?? {
            // Map certain UI-only types to closest generic CardType for tagging
            switch rawType {
            case "proposal-group", "inline-info", "list", "clarify-questions", "routine-overview": return .summary
            default: return .summary
            }
        }()

        let publishedAt = (data["created_at"] as? Timestamp)?.dateValue()
            ?? (data["updated_at"] as? Timestamp)?.dateValue()
        
        return CanvasCardModel(
            id: doc.documentID,
            type: cardType,
            status: status,
            lane: lane,
            title: title,
            subtitle: subtitle,
            data: modelData,
            width: width,
            actions: actions,
            menuItems: menuItems,
            meta: meta,
            publishedAt: publishedAt
        )
    }

    private static func parseActions(array: Any?) -> [CardAction]? {
        guard let arr = array as? [[String: Any]] else { return nil }
        return arr.compactMap { a in
            guard let kind = a["kind"] as? String ?? a["type"] as? String,
                  let label = a["label"] as? String ?? a["title"] as? String else { return nil }
            let styleStr = a["style"] as? String
            let style = styleStr.flatMap { CardActionStyle(rawValue: $0) }
            let icon = a["iconSystemName"] as? String ?? a["icon"] as? String
            return CardAction(kind: kind, label: label, style: style, iconSystemName: icon)
        }
    }
}
