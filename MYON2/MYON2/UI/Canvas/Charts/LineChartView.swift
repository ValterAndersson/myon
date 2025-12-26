import SwiftUI
import Charts

/// Line chart for time series data (e.g., e1RM trends, weekly volume)
@available(iOS 16.0, *)
public struct LineChartView: View {
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
                    LineMark(
                        x: .value(spec.data?.xAxis?.label ?? "X", point.x),
                        y: .value(spec.data?.yAxis?.label ?? "Y", point.y)
                    )
                    .foregroundStyle(s.color.color)
                    .interpolationMethod(.catmullRom)
                    
                    // Add point markers
                    PointMark(
                        x: .value(spec.data?.xAxis?.label ?? "X", point.x),
                        y: .value(spec.data?.yAxis?.label ?? "Y", point.y)
                    )
                    .foregroundStyle(s.color.color)
                    .symbolSize(30)
                }
                .foregroundStyle(by: .value("Series", s.name))
            }
            
            // Annotations (threshold lines)
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
        .chartYScale(domain: yDomain)
        .chartXAxis {
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
        .chartLegend(.hidden)  // We use custom legend
        .frame(minHeight: 180)
        .padding(.horizontal, Space.xs)
    }
    
    /// Compute Y domain with some padding
    private var yDomain: ClosedRange<Double> {
        guard let series = spec.data?.series else { return 0...100 }
        
        let allY = series.flatMap { $0.points.map { $0.y } }
        guard !allY.isEmpty else { return 0...100 }
        
        let minY = spec.data?.yAxis?.min ?? allY.min()!
        let maxY = spec.data?.yAxis?.max ?? allY.max()!
        
        // Add 10% padding
        let padding = (maxY - minY) * 0.1
        return (minY - padding)...(maxY + padding)
    }
    
    @ViewBuilder
    private func legendView(series: [ChartSeries]) -> some View {
        HStack(spacing: Space.md) {
            ForEach(series) { s in
                HStack(spacing: Space.xs) {
                    Circle()
                        .fill(s.color.color)
                        .frame(width: 8, height: 8)
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
struct LineChartView_Previews: PreviewProvider {
    static var previews: some View {
        let spec = VisualizationSpec(
            chartType: .line,
            title: "Squat e1RM Trend",
            subtitle: "Last 8 weeks",
            data: ChartData(
                xAxis: ChartAxis(key: "week", label: "Week", type: "number"),
                yAxis: ChartAxis(key: "e1rm", label: "e1RM (kg)", unit: "kg"),
                series: [
                    ChartSeries(
                        name: "Squat",
                        color: .primary,
                        points: [
                            ChartDataPoint(x: 1, y: 120),
                            ChartDataPoint(x: 2, y: 122),
                            ChartDataPoint(x: 3, y: 125),
                            ChartDataPoint(x: 4, y: 123),
                            ChartDataPoint(x: 5, y: 127),
                            ChartDataPoint(x: 6, y: 130),
                            ChartDataPoint(x: 7, y: 132),
                            ChartDataPoint(x: 8, y: 135),
                        ]
                    )
                ]
            ),
            annotations: [
                // Would need a custom initializer for preview
            ]
        )
        
        LineChartView(spec: spec)
            .padding()
            .previewLayout(.sizeThatFits)
    }
}
