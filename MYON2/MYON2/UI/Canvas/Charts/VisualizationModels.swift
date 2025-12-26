import Foundation
import SwiftUI

// MARK: - Visualization Data Models

/// Chart type enum matching visualization.schema.json
public enum ChartType: String, Codable {
    case line
    case bar
    case table
}

/// Color token enum matching design system
public enum ChartColorToken: String, Codable {
    case primary
    case secondary
    case success
    case warning
    case danger
    case neutral
    
    /// Map to design system colors
    public var color: Color {
        switch self {
        case .primary: return ColorsToken.Brand.primary
        case .secondary: return ColorsToken.Brand.secondary
        case .success: return ColorsToken.Status.success
        case .warning: return ColorsToken.Status.warning
        case .danger: return ColorsToken.Status.error
        case .neutral: return ColorsToken.Neutral.n500
        }
    }
}

/// Trend direction for table rows
public enum TrendDirection: String, Codable {
    case up
    case down
    case flat
}

// MARK: - Axis Configuration

public struct ChartAxis: Equatable, Codable {
    public let key: String?
    public let label: String?
    public let type: String?  // "date", "number", "category"
    public let unit: String?
    public let min: Double?
    public let max: Double?
    
    enum CodingKeys: String, CodingKey {
        case key, label, type, unit, min, max
    }
    
    public init(
        key: String? = nil,
        label: String? = nil,
        type: String? = nil,
        unit: String? = nil,
        min: Double? = nil,
        max: Double? = nil
    ) {
        self.key = key
        self.label = label
        self.type = type
        self.unit = unit
        self.min = min
        self.max = max
    }
}

// MARK: - Chart Data Point

public struct ChartDataPoint: Identifiable, Equatable, Codable {
    public let id: String
    public let x: Double  // For line/bar charts
    public let y: Double
    public let label: String?  // For category axis
    public let date: Date?     // For date axis
    
    enum CodingKeys: String, CodingKey {
        case id, x, y, label, date
    }
    
    public init(id: String = UUID().uuidString, x: Double, y: Double, label: String? = nil, date: Date? = nil) {
        self.id = id
        self.x = x
        self.y = y
        self.label = label
        self.date = date
    }
    
    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = (try? container.decode(String.self, forKey: .id)) ?? UUID().uuidString
        
        // Handle flexible x value (could be number, date string, or category)
        if let xNum = try? container.decode(Double.self, forKey: .x) {
            x = xNum
        } else if let xInt = try? container.decode(Int.self, forKey: .x) {
            x = Double(xInt)
        } else {
            x = 0
        }
        
        // Handle flexible y value
        if let yNum = try? container.decode(Double.self, forKey: .y) {
            y = yNum
        } else if let yInt = try? container.decode(Int.self, forKey: .y) {
            y = Double(yInt)
        } else {
            y = 0
        }
        
        label = try? container.decode(String.self, forKey: .label)
        date = try? container.decode(Date.self, forKey: .date)
    }
}

// MARK: - Chart Series (for Line/Bar charts)

public struct ChartSeries: Identifiable, Equatable, Codable {
    public let id: String
    public let name: String
    public let color: ChartColorToken
    public let points: [ChartDataPoint]
    
    enum CodingKeys: String, CodingKey {
        case name, color, points
    }
    
    public init(id: String = UUID().uuidString, name: String, color: ChartColorToken = .primary, points: [ChartDataPoint]) {
        self.id = id
        self.name = name
        self.color = color
        self.points = points
    }
    
    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = UUID().uuidString
        name = try container.decode(String.self, forKey: .name)
        color = (try? container.decode(ChartColorToken.self, forKey: .color)) ?? .primary
        points = (try? container.decode([ChartDataPoint].self, forKey: .points)) ?? []
    }
}

// MARK: - Table Row (for ranked tables)

public struct ChartTableRow: Identifiable, Equatable, Codable {
    public let id: String
    public let rank: Int
    public let label: String
    public let value: String  // Could be number or string
    public let numericValue: Double?  // For sorting
    public let delta: Double?
    public let trend: TrendDirection?
    public let sublabel: String?
    
    enum CodingKeys: String, CodingKey {
        case rank, label, value, delta, trend, sublabel
    }
    
    public init(
        id: String = UUID().uuidString,
        rank: Int,
        label: String,
        value: String,
        numericValue: Double? = nil,
        delta: Double? = nil,
        trend: TrendDirection? = nil,
        sublabel: String? = nil
    ) {
        self.id = id
        self.rank = rank
        self.label = label
        self.value = value
        self.numericValue = numericValue
        self.delta = delta
        self.trend = trend
        self.sublabel = sublabel
    }
    
    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = UUID().uuidString
        rank = (try? container.decode(Int.self, forKey: .rank)) ?? 0
        label = (try? container.decode(String.self, forKey: .label)) ?? ""
        
        // Value can be number or string
        if let numValue = try? container.decode(Double.self, forKey: .value) {
            value = String(format: "%.1f", numValue)
            numericValue = numValue
        } else if let intValue = try? container.decode(Int.self, forKey: .value) {
            value = String(intValue)
            numericValue = Double(intValue)
        } else if let strValue = try? container.decode(String.self, forKey: .value) {
            value = strValue
            numericValue = Double(strValue)
        } else {
            value = ""
            numericValue = nil
        }
        
        delta = try? container.decode(Double.self, forKey: .delta)
        trend = try? container.decode(TrendDirection.self, forKey: .trend)
        sublabel = try? container.decode(String.self, forKey: .sublabel)
    }
}

// MARK: - Table Column Definition

public struct ChartTableColumn: Identifiable, Equatable, Codable {
    public let id: String
    public let key: String
    public let label: String
    public let width: String?  // "narrow", "medium", "wide"
    public let align: String?  // "left", "center", "right"
    
    enum CodingKeys: String, CodingKey {
        case key, label, width, align
    }
    
    public init(id: String = UUID().uuidString, key: String, label: String, width: String? = nil, align: String? = nil) {
        self.id = id
        self.key = key
        self.label = label
        self.width = width
        self.align = align
    }
    
    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = UUID().uuidString
        key = (try? container.decode(String.self, forKey: .key)) ?? ""
        label = (try? container.decode(String.self, forKey: .label)) ?? ""
        width = try? container.decode(String.self, forKey: .width)
        align = try? container.decode(String.self, forKey: .align)
    }
}

// MARK: - Chart Annotation

public struct ChartAnnotation: Identifiable, Equatable, Codable {
    public let id: String
    public let type: String  // "trend_line", "threshold", "marker", "range"
    public let label: String?
    public let value: Double?
    public let slope: Double?  // For trend_line
    public let color: ChartColorToken?
    
    enum CodingKeys: String, CodingKey {
        case type, label, value, slope, color
    }
    
    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = UUID().uuidString
        type = (try? container.decode(String.self, forKey: .type)) ?? ""
        label = try? container.decode(String.self, forKey: .label)
        value = try? container.decode(Double.self, forKey: .value)
        slope = try? container.decode(Double.self, forKey: .slope)
        color = try? container.decode(ChartColorToken.self, forKey: .color)
    }
}

// MARK: - Chart Data Container

public struct ChartData: Equatable, Codable {
    public let xAxis: ChartAxis?
    public let yAxis: ChartAxis?
    public let series: [ChartSeries]?
    public let rows: [ChartTableRow]?
    public let columns: [ChartTableColumn]?
    
    enum CodingKeys: String, CodingKey {
        case xAxis = "x_axis"
        case yAxis = "y_axis"
        case series, rows, columns
    }
    
    public init(
        xAxis: ChartAxis? = nil,
        yAxis: ChartAxis? = nil,
        series: [ChartSeries]? = nil,
        rows: [ChartTableRow]? = nil,
        columns: [ChartTableColumn]? = nil
    ) {
        self.xAxis = xAxis
        self.yAxis = yAxis
        self.series = series
        self.rows = rows
        self.columns = columns
    }
}

// MARK: - Visualization Spec (Full content payload)

public struct VisualizationSpec: Equatable, Codable {
    public let chartType: ChartType
    public let title: String
    public let subtitle: String?
    public let data: ChartData?
    public let annotations: [ChartAnnotation]?
    public let metricKey: String?
    public let emptyState: String?
    
    enum CodingKeys: String, CodingKey {
        case chartType = "chart_type"
        case title, subtitle, data, annotations
        case metricKey = "metric_key"
        case emptyState = "empty_state"
    }
    
    public init(
        chartType: ChartType,
        title: String,
        subtitle: String? = nil,
        data: ChartData? = nil,
        annotations: [ChartAnnotation]? = nil,
        metricKey: String? = nil,
        emptyState: String? = nil
    ) {
        self.chartType = chartType
        self.title = title
        self.subtitle = subtitle
        self.data = data
        self.annotations = annotations
        self.metricKey = metricKey
        self.emptyState = emptyState
    }
    
    /// Computed: Check if data is empty
    public var isEmpty: Bool {
        guard let data = data else { return true }
        
        switch chartType {
        case .line, .bar:
            return (data.series ?? []).isEmpty || data.series?.allSatisfy { $0.points.isEmpty } == true
        case .table:
            return (data.rows ?? []).isEmpty
        }
    }
}
