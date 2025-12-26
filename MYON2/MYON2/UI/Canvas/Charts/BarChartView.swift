import SwiftUI
import Charts

/// Bar chart for comparisons (e.g., muscle group volume distribution, current vs baseline)
@available(iOS 16.0, *)
public struct BarChartView: View {
    private let spec: VisualizationSpec
    
    public init(spec: VisualizationSpec) {
        self.spec = spec
    }
    
    public var body: some View {
        VStack(alignment: .leading, spacing: Space.sm) {
            // Chart
            if let series = spec.data?.series, !series.isEmpty {
                chartContent(series: series)
            } else {
                emptyState
            }
            
            // Legend (if multiple series)
            if let series = spec.data?.series, series.count > 1 {
                legendView(series: series)
            }
        }
    }
    
    @ViewBuilder
    private func chartContent(series: [ChartSeries]) -> some View {
        Chart {
            ForEach(series) { s in
                ForEach(s.points) { point in
                    BarMark(
                        x: .value(spec.data?.xAxis?.label ?? "Category", point.label ?? String(Int(point.x))),
                        y: .value(spec.data?.yAxis?.label ?? "Value", point.y)
                    )
                    .foregroundStyle(s.color.color.gradient)
                    .cornerRadius(CornerRadiusToken.small)
                }
            }
            
            // Threshold annotation
            if let annotations = spec.annotations {
                ForEach(annotations) { annotation in
                    if annotation.type == "threshold", let value = annotation.value {
                        RuleMark(y: .value("Threshold", value))
                            .foregroundStyle((annotation.color ?? .neutral).color.opacity(0.6))
                            .lineStyle(StrokeStyle(lineWidth: 1, dash: [5, 5]))
                            .annotation(position: .top, alignment: .leading) {
                                if let label = annotation.label {
                                    Text(label)
                                        .font(TypographyToken.caption2)
                                        .foregroundStyle(ColorsToken.Text.secondary)
                                }
                            }
                    }
                }
            }
        }
        .chartXAxisLabel(spec.data?.xAxis?.label ?? "")
        .chartYAxisLabel(spec.data?.yAxis?.label ?? "")
        .chartXAxis {
            AxisMarks(values: .automatic) { value in
                AxisValueLabel()
                    .font(TypographyToken.caption2)
                    .foregroundStyle(ColorsToken.Text.secondary)
            }
        }
        .chartYAxis {
            AxisMarks(values: .automatic(desiredCount: 5)) { value in
                AxisGridLine(stroke: StrokeStyle(lineWidth: 0.5))
                    .foregroundStyle(ColorsToken.Border.subtle)
                AxisTick(stroke: StrokeStyle(lineWidth: 0.5))
                    .foregroundStyle(ColorsToken.Border.subtle)
                AxisValueLabel()
                    .font(TypographyToken.caption2)
                    .foregroundStyle(ColorsToken.Text.secondary)
            }
        }
        .chartLegend(.hidden)
        .frame(minHeight: 180)
        .padding(.horizontal, Space.xs)
    }
    
    @ViewBuilder
    private func legendView(series: [ChartSeries]) -> some View {
        HStack(spacing: Space.md) {
            ForEach(series) { s in
                HStack(spacing: Space.xs) {
                    RoundedRectangle(cornerRadius: 2)
                        .fill(s.color.color)
                        .frame(width: 12, height: 8)
                    Text(s.name)
                        .font(TypographyToken.caption)
                        .foregroundStyle(ColorsToken.Text.secondary)
                }
            }
        }
        .padding(.horizontal, Space.sm)
    }
    
    private var emptyState: some View {
        RoundedRectangle(cornerRadius: CornerRadiusToken.medium, style: .continuous)
            .stroke(ColorsToken.Border.subtle, lineWidth: StrokeWidthToken.hairline)
            .background(ColorsToken.Neutral.n50)
            .frame(minHeight: 160)
            .overlay(
                MyonText(spec.emptyState ?? "No data available", style: .callout, color: ColorsToken.Text.secondary, align: .center)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            )
    }
}

// MARK: - Preview

@available(iOS 16.0, *)
struct BarChartView_Previews: PreviewProvider {
    static var previews: some View {
        let spec = VisualizationSpec(
            chartType: .bar,
            title: "Weekly Volume by Muscle",
            subtitle: "Last 4 weeks average",
            data: ChartData(
                xAxis: ChartAxis(key: "muscle", label: "Muscle Group", type: "category"),
                yAxis: ChartAxis(key: "sets", label: "Weekly Sets", unit: "sets"),
                series: [
                    ChartSeries(
                        name: "Volume",
                        color: .primary,
                        points: [
                            ChartDataPoint(x: 0, y: 18, label: "Chest"),
                            ChartDataPoint(x: 1, y: 15, label: "Back"),
                            ChartDataPoint(x: 2, y: 20, label: "Quads"),
                            ChartDataPoint(x: 3, y: 12, label: "Hams"),
                            ChartDataPoint(x: 4, y: 10, label: "Shoulders"),
                            ChartDataPoint(x: 5, y: 8, label: "Arms"),
                        ]
                    )
                ]
            )
        )
        
        BarChartView(spec: spec)
            .padding()
            .previewLayout(.sizeThatFits)
    }
}
