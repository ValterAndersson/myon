import SwiftUI

// MARK: - Exercise Section Model (Render Model)

/// Unified render model for exercise block headers and state.
/// The actual set content is injected into ExerciseSection as a ViewBuilder.
/// This keeps the model lean and focused on header/container presentation.
struct ExerciseSectionModel: Identifiable, Equatable {
    typealias ID = String
    
    /// Display mode determines density and available controls
    enum Mode: Equatable {
        case planning    // Canvas/workout editor - medium density, menu actions
        case execution   // FocusMode active workout - largest, active indicator
        case readOnly    // History workout detail - most compact, minimal controls
    }
    
    let id: ID
    let mode: Mode
    
    /// Exercise name
    let title: String
    
    /// Optional subtitle (equipment, muscle group, notes)
    let subtitle: String?
    
    /// Optional index label ("1", "A1", etc) - shown in readOnly primarily
    let indexLabel: String?
    
    /// Whether this exercise is currently active (execution mode only)
    let isActive: Bool
    
    /// Available menu actions - empty for readOnly, execution may have minimal
    let menuItems: [ExerciseMenuItem]
    
    init(
        id: String,
        mode: Mode,
        title: String,
        subtitle: String? = nil,
        indexLabel: String? = nil,
        isActive: Bool = false,
        menuItems: [ExerciseMenuItem] = []
    ) {
        self.id = id
        self.mode = mode
        self.title = title
        self.subtitle = subtitle
        self.indexLabel = indexLabel
        self.isActive = isActive
        self.menuItems = menuItems
    }
}

// MARK: - Exercise Menu Items

enum ExerciseMenuItem: String, Equatable, CaseIterable {
    case info
    case swap
    case remove
    
    var label: String {
        switch self {
        case .info: return "Exercise Info"
        case .swap: return "Swap Exercise"
        case .remove: return "Remove"
        }
    }
    
    var icon: String {
        switch self {
        case .info: return "info.circle"
        case .swap: return "arrow.triangle.2.circlepath"
        case .remove: return "trash"
        }
    }
    
    var isDestructive: Bool {
        self == .remove
    }
}

// MARK: - Convenience Factories

extension ExerciseSectionModel {
    /// Factory for read-only history exercise sections
    static func readOnly(
        id: String,
        title: String,
        indexLabel: String? = nil,
        subtitle: String? = nil
    ) -> ExerciseSectionModel {
        ExerciseSectionModel(
            id: id,
            mode: .readOnly,
            title: title,
            subtitle: subtitle,
            indexLabel: indexLabel,
            isActive: false,
            menuItems: []
        )
    }
    
    /// Factory for planning mode exercise sections
    static func planning(
        id: String,
        title: String,
        subtitle: String? = nil,
        menuItems: [ExerciseMenuItem] = [.info, .swap, .remove]
    ) -> ExerciseSectionModel {
        ExerciseSectionModel(
            id: id,
            mode: .planning,
            title: title,
            subtitle: subtitle,
            indexLabel: nil,
            isActive: false,
            menuItems: menuItems
        )
    }
    
    /// Factory for execution mode exercise sections
    static func execution(
        id: String,
        title: String,
        subtitle: String? = nil,
        isActive: Bool = false,
        menuItems: [ExerciseMenuItem] = []
    ) -> ExerciseSectionModel {
        ExerciseSectionModel(
            id: id,
            mode: .execution,
            title: title,
            subtitle: subtitle,
            indexLabel: nil,
            isActive: isActive,
            menuItems: menuItems
        )
    }
}
