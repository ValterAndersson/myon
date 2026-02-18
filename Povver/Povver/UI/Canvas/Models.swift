import SwiftUI

// MARK: - Environment Key for Card Lookup

public struct CanvasCardsKey: EnvironmentKey {
    public static let defaultValue: [CanvasCardModel] = []
}

public extension EnvironmentValues {
    var canvasCards: [CanvasCardModel] {
        get { self[CanvasCardsKey.self] }
        set { self[CanvasCardsKey.self] = newValue }
    }
}

// MARK: - Card Types

public enum CardLane: String, Codable, CaseIterable { case workout, analysis, system }
public enum CardStatus: String, Codable, CaseIterable { case proposed, active, accepted, rejected, expired, completed }

public enum CardType: String, Codable, CaseIterable {
    case instruction, analysis_task, visualization, table, summary, followup_prompt
    case session_plan, current_exercise, set_target, set_result, note, coach_proposal
    case routine_summary  // Multi-day routine draft anchor
    case analysis_summary  // Analysis Agent progress insights
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

// MARK: - Set Ladder Types

public enum SetType: String, Codable, CaseIterable {
    case warmup = "warmup"
    case working = "working"
    case dropSet = "drop_set"
    case failureSet = "failure_set"
}

public struct PlanSet: Identifiable, Equatable, Codable {
    public let id: String
    public var type: SetType?          // warmup, working (nil defaults to working)
    public var reps: Int
    public var weight: Double?         // kg
    public var rir: Int?               // null for warm-ups
    public var isLinkedToBase: Bool    // true = uses base prescription (default for working sets)
    
    // For active workout (Phase 2)
    public var isCompleted: Bool?
    public var actualReps: Int?
    public var actualWeight: Double?
    public var actualRir: Int?
    
    enum CodingKeys: String, CodingKey {
        case id, type, reps, weight, rir, target
        case isLinkedToBase = "is_linked_to_base"
        case isCompleted = "is_completed"
        case actualReps = "actual_reps"
        case actualWeight = "actual_weight"
        case actualRir = "actual_rir"
    }
    
    public init(
        id: String = UUID().uuidString,
        type: SetType? = .working,
        reps: Int = 8,
        weight: Double? = nil,
        rir: Int? = nil,
        isLinkedToBase: Bool = true,  // Working sets default linked
        isCompleted: Bool? = nil,
        actualReps: Int? = nil,
        actualWeight: Double? = nil,
        actualRir: Int? = nil
    ) {
        self.id = id
        self.type = type
        self.reps = reps
        self.weight = weight
        self.rir = rir
        self.isLinkedToBase = type != .warmup ? isLinkedToBase : false  // Warm-ups not linked
        self.isCompleted = isCompleted
        self.actualReps = actualReps
        self.actualWeight = actualWeight
        self.actualRir = actualRir
    }
    
    // Flexible decoding: handle weight_kg or weight, with target wrapper fallback
    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)

        // Try id first, generate if missing
        if let decodedId = try container.decodeIfPresent(String.self, forKey: .id) {
            id = decodedId
        } else {
            id = UUID().uuidString
        }

        type = try container.decodeIfPresent(SetType.self, forKey: .type)

        // Try target wrapper for values nested inside "target": {reps, rir, weight}
        // Agent emits sets as {id, type, target: {reps, rir, weight}}
        let targetContainer = try? container.nestedContainer(keyedBy: CodingKeys.self, forKey: .target)

        reps = (try? container.decode(Int.self, forKey: .reps))
            ?? (try? targetContainer?.decode(Int.self, forKey: .reps))
            ?? 8

        // Weight: direct → target → weight_kg alternate key
        if let w = try? container.decodeIfPresent(Double.self, forKey: .weight) {
            weight = w
        } else if let w = try? targetContainer?.decodeIfPresent(Double.self, forKey: .weight) {
            weight = w
        } else {
            let altContainer = try? decoder.container(keyedBy: AlternateSetKeys.self)
            weight = try? altContainer?.decodeIfPresent(Double.self, forKey: .weightKg)
        }

        rir = (try? container.decodeIfPresent(Int.self, forKey: .rir))
            ?? (try? targetContainer?.decodeIfPresent(Int.self, forKey: .rir))

        // Default linked to base for working sets, unlinked for warm-ups
        let decodedType = type
        let decodedLinked = try container.decodeIfPresent(Bool.self, forKey: .isLinkedToBase)
        isLinkedToBase = decodedLinked ?? (decodedType != .warmup)
        isCompleted = try container.decodeIfPresent(Bool.self, forKey: .isCompleted)
        actualReps = try container.decodeIfPresent(Int.self, forKey: .actualReps)
        actualWeight = try container.decodeIfPresent(Double.self, forKey: .actualWeight)
        actualRir = try container.decodeIfPresent(Int.self, forKey: .actualRir)
    }
    
    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(id, forKey: .id)
        try container.encodeIfPresent(type, forKey: .type)
        try container.encode(reps, forKey: .reps)
        try container.encodeIfPresent(weight, forKey: .weight)
        try container.encodeIfPresent(rir, forKey: .rir)
        try container.encode(isLinkedToBase, forKey: .isLinkedToBase)
        try container.encodeIfPresent(isCompleted, forKey: .isCompleted)
        try container.encodeIfPresent(actualReps, forKey: .actualReps)
        try container.encodeIfPresent(actualWeight, forKey: .actualWeight)
        try container.encodeIfPresent(actualRir, forKey: .actualRir)
    }

    private enum AlternateSetKeys: String, CodingKey {
        case weightKg = "weight_kg"
    }
    
    // Computed: is this a warmup set?
    public var isWarmup: Bool { type == .warmup }
}

// MARK: - Plan Exercise

public struct PlanExercise: Identifiable, Equatable, Codable {
    public let id: String              // Card-local UUID
    public let exerciseId: String?     // Reference to exercises/{id} catalog
    public let name: String
    public var sets: [PlanSet]         // Explicit per-set array
    public let primaryMuscles: [String]?
    public let equipment: String?
    public var coachNote: String?      // Guidance text
    public var position: Int?          // For ordering
    public var restBetweenSets: Int?   // Seconds
    
    enum CodingKeys: String, CodingKey {
        case id
        case exerciseId = "exercise_id"
        case name
        case sets
        case primaryMuscles = "primary_muscles"
        case equipment
        case coachNote = "coach_note"
        case position
        case restBetweenSets = "rest_between_sets"
    }
    
    // Legacy keys for decoding only (not used for encoding)
    private enum LegacyCodingKeys: String, CodingKey {
        case setCount = "set_count"
        case reps
        case rir
        case weight
    }
    
    public init(
        id: String = UUID().uuidString,
        exerciseId: String? = nil,
        name: String,
        sets: [PlanSet],
        primaryMuscles: [String]? = nil,
        equipment: String? = nil,
        coachNote: String? = nil,
        position: Int? = nil,
        restBetweenSets: Int? = nil
    ) {
        self.id = id
        self.exerciseId = exerciseId
        self.name = name
        self.sets = sets
        self.primaryMuscles = primaryMuscles
        self.equipment = equipment
        self.coachNote = coachNote
        self.position = position
        self.restBetweenSets = restBetweenSets
    }
    
    // Backwards compatibility: decode from old format (sets as Int) or new format (sets as [PlanSet])
    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(String.self, forKey: .id)
        exerciseId = try container.decodeIfPresent(String.self, forKey: .exerciseId)
        name = try container.decode(String.self, forKey: .name)
        primaryMuscles = try container.decodeIfPresent([String].self, forKey: .primaryMuscles)
        equipment = try container.decodeIfPresent(String.self, forKey: .equipment)
        coachNote = try container.decodeIfPresent(String.self, forKey: .coachNote)
        position = try container.decodeIfPresent(Int.self, forKey: .position)
        restBetweenSets = try container.decodeIfPresent(Int.self, forKey: .restBetweenSets)
        
        // Try new format first: sets as [PlanSet]
        if let planSets = try? container.decode([PlanSet].self, forKey: .sets) {
            sets = planSets
        } else {
            // Legacy format: sets as Int, with separate reps/rir/weight
            let legacyContainer = try decoder.container(keyedBy: LegacyCodingKeys.self)
            
            // Try to get set count from either key
            let setsFromMain = try? container.decode(Int.self, forKey: .sets)
            let setsFromLegacy = try? legacyContainer.decode(Int.self, forKey: .setCount)
            let setCount = setsFromMain ?? setsFromLegacy ?? 3
            
            let reps = (try? legacyContainer.decode(Int.self, forKey: .reps)) ?? 8
            let rir = try? legacyContainer.decode(Int.self, forKey: .rir)
            let weight = try? legacyContainer.decode(Double.self, forKey: .weight)
            
            // Expand to array of identical working sets
            sets = (0..<setCount).map { _ in
                PlanSet(type: .working, reps: reps, weight: weight, rir: rir)
            }
        }
    }
    
    // MARK: - Computed Properties for Summary
    
    public var warmupSets: [PlanSet] { sets.filter { $0.type == .warmup } }
    public var workingSets: [PlanSet] { sets.filter { $0.type == .working || $0.type == nil } }
    public var totalSetCount: Int { sets.count }
    public var workingWeight: Double? { workingSets.first?.weight }
    
    /// Summary line: "WU: 2 set ramp · Work: 4 × 8 @ RIR 2 · 60kg target"
    public var summaryLine: String {
        var parts: [String] = []
        
        // Warm-up summary
        if !warmupSets.isEmpty {
            parts.append("WU: \(warmupSets.count) set ramp")
        }
        
        // Working sets summary
        if !workingSets.isEmpty {
            let repText = "Work: \(workingSets.count) × \(workingSets.first?.reps ?? 8)"
            if let lastRir = workingSets.last?.rir {
                parts.append("\(repText) @ RIR \(lastRir)")
            } else {
                parts.append(repText)
            }
        }
        
        // Weight target
        if let w = workingWeight, w > 0 {
            parts.append("\(Int(w))kg target")
        }
        
        return parts.isEmpty ? "\(sets.count) sets" : parts.joined(separator: " · ")
    }
    
    // Legacy compatibility: setCount for old code
    public var setCount: Int { sets.count }
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

// ClarifyQuestion model (single source of truth)

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
    public let notes: String?  // Coach narrative caption for plan cards
    public let artifactId: String?       // Firestore artifact doc ID (for artifact-sourced cards)
    public let conversationId: String?   // Conversation/canvas ID (for artifact action routing)

    enum CodingKeys: String, CodingKey {
        case context
        case groupId = "group_id"
        case pinned
        case dismissible
        case notes
        case artifactId = "artifact_id"
        case conversationId = "conversation_id"
    }

    public init(context: String? = nil, groupId: String? = nil, pinned: Bool? = nil, dismissible: Bool? = nil, notes: String? = nil, artifactId: String? = nil, conversationId: String? = nil) {
        self.context = context
        self.groupId = groupId
        self.pinned = pinned
        self.dismissible = dismissible
        self.notes = notes
        self.artifactId = artifactId
        self.conversationId = conversationId
    }
}

public enum CanvasCardData: Equatable {
    case text(String)
    case visualization(spec: VisualizationSpec)
    case visualizationLegacy(title: String, subtitle: String?)  // For backwards compat
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
    case agentMessage(AgentMessage)
    case routineSummary(RoutineSummaryData)  // Multi-day routine draft
    case analysisSummary(AnalysisSummaryData)  // Analysis Agent progress insights
}

// MARK: - Routine Summary Types

public struct RoutineSummaryData: Equatable, Codable {
    public let name: String
    public let description: String?
    public let frequency: Int
    public let workouts: [RoutineWorkoutSummary]
    public let draftId: String?
    public let revision: Int?
    
    // CRUD mode fields - indicates whether this is create/update
    public let mode: String?           // "create" | "update"
    public let sourceRoutineId: String?  // Original routine ID if updating
    public let sourceRoutineName: String?  // Original routine name for display
    
    enum CodingKeys: String, CodingKey {
        case name, description, frequency, workouts
        case draftId = "draft_id"
        case revision, mode
        case sourceRoutineId = "source_routine_id"
        case sourceRoutineName = "source_routine_name"
    }
    
    public init(
        name: String,
        description: String? = nil,
        frequency: Int,
        workouts: [RoutineWorkoutSummary],
        draftId: String? = nil,
        revision: Int? = nil,
        mode: String? = nil,
        sourceRoutineId: String? = nil,
        sourceRoutineName: String? = nil
    ) {
        self.name = name
        self.description = description
        self.frequency = frequency
        self.workouts = workouts
        self.draftId = draftId
        self.revision = revision
        self.mode = mode
        self.sourceRoutineId = sourceRoutineId
        self.sourceRoutineName = sourceRoutineName
    }
    
    /// Returns true if this is an update to an existing routine
    public var isUpdate: Bool {
        mode == "update" || sourceRoutineId != nil
    }
}

public struct RoutineWorkoutSummary: Identifiable, Equatable, Codable {
    public let id: String  // Uses card_id for identity
    public let day: Int
    public let title: String
    public let cardId: String?
    public let estimatedDuration: Int?
    public let exerciseCount: Int?
    public let muscleGroups: [String]?
    public let blocks: [PlanExercise]?  // Inline exercises from artifact (SSE path)

    enum CodingKeys: String, CodingKey {
        case id, day, title, blocks
        case cardId = "card_id"
        case estimatedDuration = "estimated_duration"
        case exerciseCount = "exercise_count"
        case muscleGroups = "muscle_groups"
    }

    public init(
        id: String = UUID().uuidString,
        day: Int,
        title: String,
        cardId: String? = nil,
        estimatedDuration: Int? = nil,
        exerciseCount: Int? = nil,
        muscleGroups: [String]? = nil,
        blocks: [PlanExercise]? = nil
    ) {
        self.id = id
        self.day = day
        self.title = title
        self.cardId = cardId
        self.estimatedDuration = estimatedDuration
        self.exerciseCount = exerciseCount
        self.muscleGroups = muscleGroups
        self.blocks = blocks
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        day = try container.decode(Int.self, forKey: .day)
        title = try container.decode(String.self, forKey: .title)
        cardId = try container.decodeIfPresent(String.self, forKey: .cardId)
        estimatedDuration = try container.decodeIfPresent(Int.self, forKey: .estimatedDuration)
        exerciseCount = try container.decodeIfPresent(Int.self, forKey: .exerciseCount)
        muscleGroups = try container.decodeIfPresent([String].self, forKey: .muscleGroups)
        blocks = try? container.decodeIfPresent([PlanExercise].self, forKey: .blocks)
        // Use cardId as id if available, derive stable fallback from day to prevent edit loss on re-parse
        id = cardId ?? "workout-day\(day)"
    }
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
    public let publishedAt: Date?
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
        meta: CardMeta? = nil,
        publishedAt: Date? = nil
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
        self.publishedAt = publishedAt
    }
}

public enum ClarifyQuestionType: String, Codable { case text, single_choice, multi_choice, yes_no }

public struct ClarifyQuestion: Identifiable, Equatable, Codable {
    public let id: String
    public let text: String
    public let options: [String]?
    public let type: ClarifyQuestionType
    
    public init(id: String = UUID().uuidString, text: String, options: [String]? = nil, type: ClarifyQuestionType = .text) {
        self.id = id
        self.text = text
        self.options = options
        self.type = type
    }
}

public struct AgentMessage: Equatable, Codable {
    public let type: String? // "thinking", "tool_running", "tool_complete", "status", etc.
    public let status: String?
    public let message: String?
    public let toolCalls: [ToolCall]?
    public let thoughts: [String]?
    
    public init(type: String? = nil, status: String? = nil, message: String? = nil, 
                toolCalls: [ToolCall]? = nil, thoughts: [String]? = nil) {
        self.type = type
        self.status = status
        self.message = message
        self.toolCalls = toolCalls
        self.thoughts = thoughts
    }
}

public struct ToolCall: Identifiable, Equatable, Codable {
    public let id: String
    public let name: String
    public let displayName: String
    public let duration: String?
    
    public init(id: String = UUID().uuidString, name: String, displayName: String, duration: String? = nil) {
        self.id = id
        self.name = name
        self.displayName = displayName
        self.duration = duration
    }
}

// MARK: - Analysis Summary Types (Analysis Agent)

public struct AnalysisSummaryData: Equatable, Codable {
    public let headline: String
    public let period: AnalysisPeriod?
    public let insights: [AnalysisInsight]
    public let recommendations: [AnalysisRecommendation]
    public let dataQuality: AnalysisDataQuality?
    
    enum CodingKeys: String, CodingKey {
        case headline
        case period
        case insights
        case recommendations
        case dataQuality = "data_quality"
    }
    
    public init(
        headline: String,
        period: AnalysisPeriod? = nil,
        insights: [AnalysisInsight] = [],
        recommendations: [AnalysisRecommendation] = [],
        dataQuality: AnalysisDataQuality? = nil
    ) {
        self.headline = headline
        self.period = period
        self.insights = insights
        self.recommendations = recommendations
        self.dataQuality = dataQuality
    }
}

public struct AnalysisPeriod: Equatable, Codable {
    public let weeks: Int
    public let end: String?
    
    public init(weeks: Int, end: String? = nil) {
        self.weeks = weeks
        self.end = end
    }
}

public struct AnalysisInsight: Identifiable, Equatable, Codable {
    public let id: String
    public let category: String  // "progressive_overload" | "volume" | "frequency" | "laggard" | "consistency" | "goal_alignment"
    public let signal: String    // Human-readable insight text
    public let trend: String     // "improving" | "stable" | "declining" | "insufficient_data"
    public let metricKey: String?
    public let value: Double?
    public let confidence: String?  // "high" | "medium" | "low"
    
    enum CodingKeys: String, CodingKey {
        case id, category, signal, trend
        case metricKey = "metric_key"
        case value, confidence
    }
    
    public init(
        id: String = UUID().uuidString,
        category: String,
        signal: String,
        trend: String = "stable",
        metricKey: String? = nil,
        value: Double? = nil,
        confidence: String? = nil
    ) {
        self.id = id
        self.category = category
        self.signal = signal
        self.trend = trend
        self.metricKey = metricKey
        self.value = value
        self.confidence = confidence
    }
    
    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = (try? container.decode(String.self, forKey: .id)) ?? UUID().uuidString
        category = try container.decode(String.self, forKey: .category)
        signal = try container.decode(String.self, forKey: .signal)
        trend = (try? container.decode(String.self, forKey: .trend)) ?? "stable"
        metricKey = try container.decodeIfPresent(String.self, forKey: .metricKey)
        value = try container.decodeIfPresent(Double.self, forKey: .value)
        confidence = try container.decodeIfPresent(String.self, forKey: .confidence)
    }
}

public struct AnalysisRecommendation: Identifiable, Equatable, Codable {
    public let id: String
    public let priority: Int  // 1-5 (1 = highest)
    public let action: String
    public let rationale: String
    public let category: String?  // "volume" | "frequency" | "exercise_selection" | "progression" | "recovery"
    
    public init(
        id: String = UUID().uuidString,
        priority: Int = 3,
        action: String,
        rationale: String,
        category: String? = nil
    ) {
        self.id = id
        self.priority = priority
        self.action = action
        self.rationale = rationale
        self.category = category
    }
    
    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = (try? container.decode(String.self, forKey: .id)) ?? UUID().uuidString
        priority = (try? container.decode(Int.self, forKey: .priority)) ?? 3
        action = try container.decode(String.self, forKey: .action)
        rationale = try container.decode(String.self, forKey: .rationale)
        category = try container.decodeIfPresent(String.self, forKey: .category)
    }
    
    enum CodingKeys: String, CodingKey {
        case id, priority, action, rationale, category
    }
}

public struct AnalysisDataQuality: Equatable, Codable {
    public let weeksWithData: Int
    public let workoutsAnalyzed: Int
    public let confidence: String  // "high" | "medium" | "low"
    public let caveats: [String]?
    
    enum CodingKeys: String, CodingKey {
        case weeksWithData = "weeks_with_data"
        case workoutsAnalyzed = "workouts_analyzed"
        case confidence
        case caveats
    }
    
    public init(
        weeksWithData: Int,
        workoutsAnalyzed: Int,
        confidence: String = "medium",
        caveats: [String]? = nil
    ) {
        self.weeksWithData = weeksWithData
        self.workoutsAnalyzed = workoutsAnalyzed
        self.confidence = confidence
        self.caveats = caveats
    }
}
