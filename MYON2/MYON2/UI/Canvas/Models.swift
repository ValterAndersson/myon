import SwiftUI

public enum CardLane: String, Codable, CaseIterable { case workout, analysis, system }
public enum CardStatus: String, Codable, CaseIterable { case proposed, active, accepted, rejected, expired, completed }

public enum CardType: String, Codable, CaseIterable {
    case instruction, analysis_task, visualization, table, summary, followup_prompt
    case session_plan, current_exercise, set_target, set_result, note, coach_proposal
}

public enum CardWidth: String, Codable, CaseIterable {
    case oneThird
    case oneHalf
    case full
    public var columns: Int {
        switch self {
        // 12-column grid for predictable percentage widths
        case .oneThird: return 4
        case .oneHalf: return 6
        case .full: return 12
        }
    }
}

public struct PlanExercise: Identifiable, Equatable, Codable {
    public let id: String
    public let name: String
    public let sets: Int
    public init(id: String = UUID().uuidString, name: String, sets: Int) {
        self.id = id; self.name = name; self.sets = sets
    }
}

public struct AgentStreamStep: Identifiable, Equatable, Codable {
    public enum Kind: String, Codable { case thinking, info, lookup, result }
    public let id: String
    public let kind: Kind
    public let text: String?
    public let durationMs: Int?
    public init(id: String = UUID().uuidString, kind: Kind, text: String? = nil, durationMs: Int? = nil) {
        self.id = id; self.kind = kind; self.text = text; self.durationMs = durationMs
    }
}

public struct ListOption: Identifiable, Equatable, Codable {
    public let id: String
    public let title: String
    public let subtitle: String?
    public let iconSystemName: String?
    public init(id: String = UUID().uuidString, title: String, subtitle: String? = nil, iconSystemName: String? = nil) {
        self.id = id; self.title = title; self.subtitle = subtitle; self.iconSystemName = iconSystemName
    }
}

public enum ClarifyQuestionType: String, Codable { case text, choice }

public struct ClarifyQuestion: Identifiable, Equatable, Codable {
    public let id: String
    public let label: String
    public let type: ClarifyQuestionType
    public let options: [String]?
    public init(id: String = UUID().uuidString, label: String, type: ClarifyQuestionType, options: [String]? = nil) {
        self.id = id; self.label = label; self.type = type; self.options = options
    }
}

public enum CardActionStyle: String, Codable { case primary, secondary, ghost, destructive }

public struct CardAction: Identifiable, Equatable, Codable {
    public let id: String
    public let kind: String
    public let label: String
    public let style: CardActionStyle?
    public let iconSystemName: String?
    public let payload: [String: String]?
    public init(id: String = UUID().uuidString, kind: String, label: String, style: CardActionStyle? = nil, iconSystemName: String? = nil, payload: [String: String]? = nil) {
        self.id = id
        self.kind = kind
        self.label = label
        self.style = style
        self.iconSystemName = iconSystemName
        self.payload = payload
    }
}

public struct CardMeta: Equatable, Codable {
    public let context: String?
    public let groupId: String?
    public let pinned: Bool?
    public let dismissible: Bool?
    public init(context: String? = nil, groupId: String? = nil, pinned: Bool? = nil, dismissible: Bool? = nil) {
        self.context = context; self.groupId = groupId; self.pinned = pinned; self.dismissible = dismissible
    }
}

public enum CanvasCardData: Equatable {
    case text(String)
    case visualization(title: String, subtitle: String?)
    case chat(lines: [String])
    case suggestion(title: String, rationale: String?)
    case sessionPlan(exercises: [PlanExercise])
    case agentStream(steps: [AgentStreamStep])
    case programDay(title: String, exercises: [PlanExercise])
    case list(options: [ListOption])
    case inlineInfo(String)
    case groupHeader(title: String)
    case clarifyQuestions([ClarifyQuestion])
    case routineOverview(split: String, days: Int, notes: String?)
}

public struct CanvasCardModel: Identifiable, Equatable {
    public let id: String
    public let type: CardType
    public let status: CardStatus
    public let lane: CardLane
    public let title: String?
    public let subtitle: String?
    public let data: CanvasCardData
    public let width: CardWidth
    public let actions: [CardAction]
    public let menuItems: [CardAction]
    public let meta: CardMeta?
    public init(
        id: String = UUID().uuidString,
        type: CardType,
        status: CardStatus = .active,
        lane: CardLane = .analysis,
        title: String? = nil,
        subtitle: String? = nil,
        data: CanvasCardData,
        width: CardWidth = .full,
        actions: [CardAction] = [],
        menuItems: [CardAction] = [],
        meta: CardMeta? = nil
    ) {
        self.id = id
        self.type = type
        self.status = status
        self.lane = lane
        self.title = title
        self.subtitle = subtitle
        self.data = data
        self.width = width
        self.actions = actions
        self.menuItems = menuItems
        self.meta = meta
    }
}


