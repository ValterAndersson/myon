import SwiftUI

struct RecommendationCardView: View {
    let recommendation: AgentRecommendation
    let isProcessing: Bool
    var onAccept: (() -> Void)?
    var onReject: (() -> Void)?

    var body: some View {
        VStack(alignment: .leading, spacing: Space.sm) {
            // Header: trigger pill + timestamp
            HStack {
                Text(triggerLabel)
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundColor(Color.accent)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 3)
                    .background(Color.accent.opacity(0.12))
                    .clipShape(Capsule())

                Spacer()

                Text(relativeTime)
                    .font(.system(size: 12))
                    .foregroundColor(Color.textTertiary)
            }

            // Summary
            Text(recommendation.recommendation.summary)
                .font(.system(size: 15, weight: .semibold))
                .foregroundColor(Color.textPrimary)

            // Rationale
            if let rationale = recommendation.recommendation.rationale, !rationale.isEmpty {
                Text(rationale)
                    .font(.system(size: 13))
                    .foregroundColor(Color.textSecondary)
                    .lineLimit(3)
            }

            // Changes preview
            if !recommendation.recommendation.changes.isEmpty {
                let change = recommendation.recommendation.changes[0]
                Text(change.rationale ?? changeDescription(change))
                    .font(.system(size: 12, weight: .medium).monospacedDigit())
                    .foregroundColor(Color.textSecondary)
                    .padding(.horizontal, Space.sm)
                    .padding(.vertical, 4)
                    .background(Color.bg)
                    .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.small))
            }

            // Actions or status
            if recommendation.state == "pending_review" {
                HStack(spacing: Space.sm) {
                    Button(action: { onReject?() }) {
                        Text("Decline")
                            .font(.system(size: 14, weight: .medium))
                            .foregroundColor(Color.destructive)
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 10)
                            .overlay(
                                RoundedRectangle(cornerRadius: CornerRadiusToken.small)
                                    .stroke(Color.destructive.opacity(0.4), lineWidth: 1)
                            )
                    }
                    .disabled(isProcessing)

                    Button(action: { onAccept?() }) {
                        HStack(spacing: 4) {
                            if isProcessing {
                                ProgressView()
                                    .scaleEffect(0.7)
                                    .tint(.white)
                            }
                            Text("Accept")
                                .font(.system(size: 14, weight: .semibold))
                        }
                        .foregroundColor(.white)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 10)
                        .background(Color.accent)
                        .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.small))
                    }
                    .disabled(isProcessing)
                }
                .padding(.top, Space.xs)
            } else if recommendation.state == "applied" {
                HStack {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundColor(.green)
                        .font(.system(size: 14))
                    Text(recommendation.appliedBy == "agent" ? "Auto-applied" : "Applied")
                        .font(.system(size: 13, weight: .medium))
                        .foregroundColor(Color.textSecondary)
                }
                .padding(.top, Space.xs)
            }
        }
        .padding(Space.md)
        .background(Color.surface)
        .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.medium))
    }

    private var triggerLabel: String {
        switch recommendation.trigger {
        case "post_workout": return "Post-workout"
        case "weekly_review": return "Weekly review"
        default: return recommendation.trigger.capitalized
        }
    }

    private var relativeTime: String {
        let interval = Date().timeIntervalSince(recommendation.createdAt)
        if interval < 60 { return "now" }
        if interval < 3600 { return "\(Int(interval / 60))m ago" }
        if interval < 86400 { return "\(Int(interval / 3600))h ago" }
        return "\(Int(interval / 86400))d ago"
    }

    private func changeDescription(_ change: RecommendationChange) -> String {
        let from = formatValue(change.from)
        let to = formatValue(change.to)
        return "\(from) → \(to)"
    }

    private func formatValue(_ value: AnyCodable) -> String {
        switch value.value {
        case let n as Int: return "\(n)kg"
        case let n as Double: return String(format: "%.1fkg", n)
        case let s as String: return s
        default: return "—"
        }
    }
}
