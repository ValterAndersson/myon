import Foundation

enum WeightUnit: String, CaseIterable {
    case kg, lbs

    var label: String { rawValue }

    /// Initialize from Firestore weight_format value ("kilograms" or "pounds")
    init(firestoreFormat: String?) {
        self = (firestoreFormat == "pounds") ? .lbs : .kg
    }

    /// Firestore weight_format value
    var firestoreFormat: String { self == .lbs ? "pounds" : "kilograms" }
}

enum WeightFormatter {
    private static let kgToLbs: Double = 2.20462

    /// Convert kg storage value to display unit
    static func display(_ kg: Double, unit: WeightUnit) -> Double {
        unit == .lbs ? kg * kgToLbs : kg
    }

    /// Convert user input back to kg for storage
    static func toKg(_ value: Double, from unit: WeightUnit) -> Double {
        unit == .lbs ? value / kgToLbs : value
    }

    /// Format weight for display with unit suffix. Returns "—" for nil/zero.
    static func format(_ kg: Double?, unit: WeightUnit) -> String {
        guard let kg, kg > 0 else { return "—" }
        let displayed = display(kg, unit: unit)
        let rounded = roundForDisplay(displayed)
        return truncateTrailingZeros(rounded) + " " + unit.label
    }

    /// Format weight for display WITHOUT unit suffix (for use in text fields, grids).
    /// Returns "—" for nil/zero.
    static func formatValue(_ kg: Double?, unit: WeightUnit) -> String {
        guard let kg, kg > 0 else { return "—" }
        let displayed = display(kg, unit: unit)
        let rounded = roundForDisplay(displayed)
        return truncateTrailingZeros(rounded)
    }

    /// Round to nearest plate increment (for prescriptions and progression suggestions)
    static func roundToPlate(_ value: Double, unit: WeightUnit) -> Double {
        let increment: Double = unit == .lbs ? 5.0 : 2.5
        return (value / increment).rounded() * increment
    }

    /// Round for display (1 decimal place)
    static func roundForDisplay(_ value: Double) -> Double {
        (value * 10).rounded() / 10
    }

    /// Weight increment for progression (smallest plate jump)
    static func plateIncrement(unit: WeightUnit) -> Double {
        unit == .lbs ? 5.0 : 2.5
    }

    /// Format a plate increment label (e.g., "+2.5kg" or "+5lbs")
    static func incrementLabel(unit: WeightUnit) -> String {
        let inc = plateIncrement(unit: unit)
        return "+\(truncateTrailingZeros(inc))\(unit.label)"
    }

    private static func truncateTrailingZeros(_ value: Double) -> String {
        if value.truncatingRemainder(dividingBy: 1) == 0 {
            return String(Int(value))
        }
        return String(format: "%.1f", value)
    }
}
