import SwiftUI

/// Canvas card for Analysis Agent progress insights
public struct AnalysisSummaryCard: View {
    private let model: CanvasCardModel
    private let data: AnalysisSummaryData
    
    public init(model: CanvasCardModel, data: AnalysisSummaryData) {
        self.model = model
        self.data = data
    }
    
    public var body: some View {
        VStack(alignment: .leading, spacing: Space.md) {
            // Header with headline and period
            headerView
            
            // Insights section
            if !data.insights.isEmpty {
                insightsSection
            }
            
            // Recommendations section
            if !data.recommendations.isEmpty {
                recommendationsSection
            }
            
            // Data quality footer
            if let dq = data.dataQuality {
                dataQualityBadge(dq)
            }
            
            // Actions
            if !model.actions.isEmpty {
                actionsRow
            }
        }
        .padding(Space.md)
        .background(ColorsToken.Surface.primary)
        .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.large, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: CornerRadiusToken.large, style: .continuous)
                .stroke(ColorsToken.Border.subtle, lineWidth: StrokeWidthToken.hairline)
        )
    }
    
    // MARK: - Header
    
    @ViewBuilder
    private var headerView: some View {
        VStack(alignment: .leading, spacing: Space.xxs) {
            HStack {
                Image(systemName: "chart.line.uptrend.xyaxis")
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundStyle(ColorsToken.Brand.primary)
                
                Text("Progress Analysis")
                    .font(TypographyToken.caption)
                    .foregroundStyle(ColorsToken.Text.secondary)
                
                Spacer()
                
                // Period badge
                if let period = data.period {
                    Text("\(period.weeks) weeks")
                        .font(TypographyToken.caption2)
                        .padding(.horizontal, Space.xs)
                        .padding(.vertical, 2)
                        .background(ColorsToken.Neutral.n100)
                        .foregroundStyle(ColorsToken.Text.secondary)
                        .clipShape(Capsule())
                }
            }
            
            Text(data.headline)
                .font(TypographyToken.headlineBold)
                .foregroundStyle(ColorsToken.Text.primary)
        }
    }
    
    // MARK: - Insights Section
    
    @ViewBuilder
    private var insightsSection: some View {
        VStack(alignment: .leading, spacing: Space.sm) {
            Text("Insights")
                .font(TypographyToken.captionBold)
                .foregroundStyle(ColorsToken.Text.secondary)
            
            ForEach(data.insights.prefix(5)) { insight in
                insightRow(insight)
            }
        }
    }
    
    @ViewBuilder
    private func insightRow(_ insight: AnalysisInsight) -> some View {
        HStack(alignment: .top, spacing: Space.sm) {
            // Trend indicator
            trendIcon(insight.trend)
                .frame(width: 20, height: 20)
            
            VStack(alignment: .leading, spacing: 2) {
                Text(insight.signal)
                    .font(TypographyToken.callout)
                    .foregroundStyle(ColorsToken.Text.primary)
                
                Text(insight.category.replacingOccurrences(of: "_", with: " ").capitalized)
                    .font(TypographyToken.caption2)
                    .foregroundStyle(ColorsToken.Text.tertiary)
            }
            
            Spacer()
        }
        .padding(.vertical, Space.xxs)
    }
    
    @ViewBuilder
    private func trendIcon(_ trend: String) -> some View {
        let (icon, color): (String, Color) = {
            switch trend {
            case "improving": return ("arrow.up.circle.fill", ColorsToken.Status.success)
            case "declining": return ("arrow.down.circle.fill", ColorsToken.Status.error)
            case "insufficient_data": return ("questionmark.circle.fill", ColorsToken.Text.tertiary)
            default: return ("equal.circle.fill", ColorsToken.Text.secondary)
            }
        }()
        
        Image(systemName: icon)
            .foregroundStyle(color)
            .font(.system(size: 18))
    }
    
    // MARK: - Recommendations Section
    
    @ViewBuilder
    private var recommendationsSection: some View {
        VStack(alignment: .leading, spacing: Space.sm) {
            Text("Recommendations")
                .font(TypographyToken.captionBold)
                .foregroundStyle(ColorsToken.Text.secondary)
            
            ForEach(data.recommendations.prefix(5)) { rec in
                recommendationRow(rec)
            }
        }
    }
    
    @ViewBuilder
    private func recommendationRow(_ rec: AnalysisRecommendation) -> some View {
        HStack(alignment: .top, spacing: Space.sm) {
            // Priority badge
            priorityBadge(rec.priority)
            
            VStack(alignment: .leading, spacing: 2) {
                Text(rec.action)
                    .font(TypographyToken.callout)
                    .fontWeight(.medium)
                    .foregroundStyle(ColorsToken.Text.primary)
                
                Text(rec.rationale)
                    .font(TypographyToken.caption)
                    .foregroundStyle(ColorsToken.Text.secondary)
            }
            
            Spacer()
        }
        .padding(Space.xs)
        .background(ColorsToken.Neutral.n50)
        .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.small))
    }
    
    @ViewBuilder
    private func priorityBadge(_ priority: Int) -> some View {
        Text("P\(priority)")
            .font(TypographyToken.caption2)
            .fontWeight(.bold)
            .foregroundStyle(priority <= 2 ? Color.white : ColorsToken.Text.secondary)
            .frame(width: 24, height: 24)
            .background(priorityColor(priority))
            .clipShape(RoundedRectangle(cornerRadius: 6))
    }
    
    private func priorityColor(_ priority: Int) -> Color {
        switch priority {
        case 1: return ColorsToken.Status.error
        case 2: return ColorsToken.Status.warning
        case 3: return ColorsToken.Text.secondary
        default: return ColorsToken.Neutral.n300
        }
    }
    
    // MARK: - Data Quality
    
    @ViewBuilder
    private func dataQualityBadge(_ dq: AnalysisDataQuality) -> some View {
        HStack(spacing: Space.xs) {
            Image(systemName: confidenceIcon(dq.confidence))
                .font(.system(size: 12))
            
            Text("\(dq.workoutsAnalyzed) workouts · \(dq.weeksWithData) weeks")
                .font(TypographyToken.caption2)
            
            Text(dq.confidence.capitalized)
                .font(TypographyToken.caption2)
                .fontWeight(.medium)
        }
        .foregroundStyle(confidenceColor(dq.confidence))
        .padding(.top, Space.xs)
    }
    
    private func confidenceIcon(_ confidence: String) -> String {
        switch confidence {
        case "high": return "checkmark.seal.fill"
        case "medium": return "checkmark.circle.fill"
        default: return "exclamationmark.triangle.fill"
        }
    }
    
    private func confidenceColor(_ confidence: String) -> Color {
        switch confidence {
        case "high": return ColorsToken.Status.success
        case "medium": return ColorsToken.Text.secondary
        default: return ColorsToken.Status.warning
        }
    }
    
    // MARK: - Actions
    
    @ViewBuilder
    private var actionsRow: some View {
        HStack(spacing: Space.sm) {
            ForEach(model.actions) { action in
                actionButton(action)
            }
            Spacer()
        }
        .padding(.top, Space.xs)
    }
    
    @ViewBuilder
    private func actionButton(_ action: CardAction) -> some View {
        Button {
            // Action handling
        } label: {
            HStack(spacing: Space.xs) {
                if let iconName = action.iconSystemName {
                    Image(systemName: iconName)
                        .font(.system(size: 12, weight: .medium))
                }
                Text(action.label)
                    .font(TypographyToken.caption)
            }
            .padding(.horizontal, Space.sm)
            .padding(.vertical, Space.xs)
            .background(actionBackground(style: action.style))
            .foregroundStyle(actionForeground(style: action.style))
            .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.small))
        }
    }
    
    private func actionBackground(style: CardActionStyle?) -> Color {
        switch style {
        case .primary: return ColorsToken.Brand.primary
        case .destructive: return ColorsToken.Status.error
        case .ghost, .none: return ColorsToken.Neutral.n100
        default: return ColorsToken.Neutral.n200
        }
    }
    
    private func actionForeground(style: CardActionStyle?) -> Color {
        switch style {
        case .primary, .destructive: return ColorsToken.Text.inverse
        default: return ColorsToken.Text.primary
        }
    }
}

// MARK: - Preview

struct AnalysisSummaryCard_Previews: PreviewProvider {
    static var previews: some View {
        VStack(spacing: Space.md) {
            AnalysisSummaryCard(
                model: CanvasCardModel(
                    type: .analysis_summary,
                    data: .text(""),
                    actions: [
                        CardAction(kind: "apply_recommendations", label: "Apply to Plan", style: .primary, iconSystemName: "wand.and.stars"),
                        CardAction(kind: "dismiss", label: "Dismiss", style: .ghost, iconSystemName: "xmark")
                    ]
                ),
                data: AnalysisSummaryData(
                    headline: "Strong upper body progress, back lagging",
                    period: AnalysisPeriod(weeks: 8, end: "2024-12-26"),
                    insights: [
                        AnalysisInsight(category: "progressive_overload", signal: "Bench press e1RM up 8% over 8 weeks", trend: "improving"),
                        AnalysisInsight(category: "laggard", signal: "Back volume flat despite increased chest emphasis", trend: "declining"),
                        AnalysisInsight(category: "consistency", signal: "Training 3.2x/week average, high adherence", trend: "stable"),
                    ],
                    recommendations: [
                        AnalysisRecommendation(priority: 1, action: "Add 2 sets/week for back muscles", rationale: "Back is 40% below chest volume despite similar goals"),
                        AnalysisRecommendation(priority: 2, action: "Consider row variation swap", rationale: "Cable row may provide better lat stimulus than barbell"),
                    ],
                    dataQuality: AnalysisDataQuality(weeksWithData: 8, workoutsAnalyzed: 25, confidence: "high")
                )
            )
        }
        .padding()
        .previewLayout(.sizeThatFits)
    }
}
