import SwiftUI

/// Ranked table for movers/laggards (sorted lists with trend indicators)
public struct RankedTableView: View {
    private let spec: VisualizationSpec
    
    public init(spec: VisualizationSpec) {
        self.spec = spec
    }
    
    public var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            if let rows = spec.data?.rows, !rows.isEmpty {
                tableContent(rows: rows)
            } else {
                emptyState
            }
        }
    }
    
    @ViewBuilder
    private func tableContent(rows: [ChartTableRow]) -> some View {
        VStack(spacing: 0) {
            ForEach(rows) { row in
                tableRow(row)
                
                if row.id != rows.last?.id {
                    Divider()
                        .background(ColorsToken.Border.subtle)
                }
            }
        }
        .background(ColorsToken.Surface.primary)
        .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.medium, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: CornerRadiusToken.medium, style: .continuous)
                .stroke(ColorsToken.Border.subtle, lineWidth: StrokeWidthToken.hairline)
        )
    }
    
    @ViewBuilder
    private func tableRow(_ row: ChartTableRow) -> some View {
        HStack(spacing: Space.sm) {
            // Rank badge
            rankBadge(rank: row.rank)
            
            // Label and sublabel
            VStack(alignment: .leading, spacing: 2) {
                Text(row.label)
                    .font(TypographyToken.body)
                    .foregroundStyle(ColorsToken.Text.primary)
                
                if let sublabel = row.sublabel {
                    Text(sublabel)
                        .font(TypographyToken.caption)
                        .foregroundStyle(ColorsToken.Text.tertiary)
                }
            }
            
            Spacer()
            
            // Value and delta
            VStack(alignment: .trailing, spacing: 2) {
                HStack(spacing: Space.xs) {
                    Text(row.value)
                        .font(TypographyToken.bodyBold)
                        .foregroundStyle(ColorsToken.Text.primary)
                    
                    if let unit = spec.data?.yAxis?.unit {
                        Text(unit)
                            .font(TypographyToken.caption)
                            .foregroundStyle(ColorsToken.Text.secondary)
                    }
                }
                
                if let delta = row.delta {
                    deltaLabel(delta: delta, trend: row.trend)
                }
            }
            
            // Trend indicator
            if let trend = row.trend {
                trendIndicator(trend: trend)
            }
        }
        .padding(.horizontal, Space.md)
        .padding(.vertical, Space.sm)
    }
    
    @ViewBuilder
    private func rankBadge(rank: Int) -> some View {
        Text("\(rank)")
            .font(TypographyToken.caption2Bold)
            .foregroundStyle(rank <= 3 ? ColorsToken.Text.inverse : ColorsToken.Text.secondary)
            .frame(width: 24, height: 24)
            .background(
                Circle()
                    .fill(rankColor(rank: rank))
            )
    }
    
    private func rankColor(rank: Int) -> Color {
        switch rank {
        case 1: return ColorsToken.Brand.primary
        case 2: return ColorsToken.Brand.secondary
        case 3: return ColorsToken.Neutral.n600
        default: return ColorsToken.Neutral.n200
        }
    }
    
    @ViewBuilder
    private func deltaLabel(delta: Double, trend: TrendDirection?) -> some View {
        let isPositive = delta >= 0
        let color = trend == .up ? ColorsToken.Status.success : 
                   (trend == .down ? ColorsToken.Status.error : ColorsToken.Text.tertiary)
        
        HStack(spacing: 2) {
            Text(isPositive ? "+" : "")
                .font(TypographyToken.caption)
            Text(String(format: "%.1f", delta))
                .font(TypographyToken.caption)
        }
        .foregroundStyle(color)
    }
    
    @ViewBuilder
    private func trendIndicator(trend: TrendDirection) -> some View {
        let icon: String
        let color: Color
        
        switch trend {
        case .up:
            icon = "arrow.up.right"
            color = ColorsToken.Status.success
        case .down:
            icon = "arrow.down.right"
            color = ColorsToken.Status.error
        case .flat:
            icon = "arrow.right"
            color = ColorsToken.Text.tertiary
        }
        
        Image(systemName: icon)
            .font(.system(size: 12, weight: .medium))
            .foregroundStyle(color)
            .frame(width: 20)
    }
    
    private var emptyState: some View {
        RoundedRectangle(cornerRadius: CornerRadiusToken.medium, style: .continuous)
            .stroke(ColorsToken.Border.subtle, lineWidth: StrokeWidthToken.hairline)
            .background(ColorsToken.Neutral.n50)
            .frame(minHeight: 120)
            .overlay(
                MyonText(spec.emptyState ?? "No data available", style: .callout, color: ColorsToken.Text.secondary, align: .center)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            )
    }
}

// MARK: - Preview

struct RankedTableView_Previews: PreviewProvider {
    static var previews: some View {
        let spec = VisualizationSpec(
            chartType: .table,
            title: "Top Movers (e1RM)",
            subtitle: "Last 8 weeks",
            data: ChartData(
                yAxis: ChartAxis(unit: "kg"),
                rows: [
                    ChartTableRow(rank: 1, label: "Squat", value: "140", numericValue: 140, delta: 12.5, trend: .up, sublabel: "+9.8%"),
                    ChartTableRow(rank: 2, label: "Bench Press", value: "95", numericValue: 95, delta: 7.0, trend: .up, sublabel: "+7.9%"),
                    ChartTableRow(rank: 3, label: "Deadlift", value: "180", numericValue: 180, delta: 5.0, trend: .up, sublabel: "+2.9%"),
                    ChartTableRow(rank: 4, label: "OHP", value: "55", numericValue: 55, delta: 0.0, trend: .flat, sublabel: "0%"),
                    ChartTableRow(rank: 5, label: "Rows", value: "70", numericValue: 70, delta: -2.5, trend: .down, sublabel: "-3.4%"),
                ]
            )
        )
        
        RankedTableView(spec: spec)
            .padding()
            .previewLayout(.sizeThatFits)
    }
}
