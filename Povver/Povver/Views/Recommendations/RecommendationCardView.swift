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
                    .lineLimit(10)
            }

            // Changes preview — show up to 3 changes
            if !recommendation.recommendation.changes.isEmpty {
                let displayChanges = Array(recommendation.recommendation.changes.prefix(3))
                VStack(alignment: .leading, spacing: 2) {
                    ForEach(Array(displayChanges.enumerated()), id: \.offset) { _, change in
                        Text(changeDescription(change))
                            .font(.system(size: 12, weight: .medium).monospacedDigit())
                            .foregroundColor(Color.textSecondary)
                    }
                    if recommendation.recommendation.changes.count > 3 {
                        Text("+ \(recommendation.recommendation.changes.count - 3) more")
                            .font(.system(size: 11))
                            .foregroundColor(Color.textTertiary)
                    }
                }
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
                            Text(acceptButtonText)
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
            } else if recommendation.state == "acknowledged" {
                HStack {
                    Image(systemName: "checkmark.circle")
                        .foregroundColor(Color.textTertiary)
                        .font(.system(size: 14))
                    Text("Noted")
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

    /// "Got it" for exercise/routine scoped recs, "Accept" for template-scoped
    private var acceptButtonText: String {
        let scope = recommendation.scope
        if scope == "exercise" || scope == "routine" {
            return "Got it"
        }
        return "Accept"
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

    /// Path-aware change description — reads the path string to determine formatting
    private func changeDescription(_ change: RecommendationChange) -> String {
        let path = change.path
        let from = change.from
        let to = change.to

        if path.contains("weight_kg") {
            let fromStr = formatWeight(from)
            let toStr = formatWeight(to)
            return "\(fromStr) \u{2192} \(toStr)"
        }

        if path.contains("target_reps") || path.hasSuffix(".reps") {
            let toStr = formatNumeric(to)
            if isNull(from) {
                return "\u{2192} \(toStr) reps"
            }
            let fromStr = formatNumeric(from)
            return "\(fromStr) \u{2192} \(toStr) reps"
        }

        if path.contains("target_rir") || path.hasSuffix(".rir") {
            let toStr = formatNumeric(to)
            if isNull(from) {
                return "RIR \u{2192} \(toStr)"
            }
            let fromStr = formatNumeric(from)
            return "RIR \(fromStr) \u{2192} \(toStr)"
        }

        // Fallback
        let fromStr = formatGeneric(from)
        let toStr = formatGeneric(to)
        return "\(fromStr) \u{2192} \(toStr)"
    }

    private func isNull(_ value: AnyCodable) -> Bool {
        return value.value is NSNull
    }

    private func formatWeight(_ value: AnyCodable) -> String {
        switch value.value {
        case let n as Int: return "\(n)kg"
        case let n as Double: return String(format: n.truncatingRemainder(dividingBy: 1) == 0 ? "%.0fkg" : "%.1fkg", n)
        default: return "\u{2014}"
        }
    }

    private func formatNumeric(_ value: AnyCodable) -> String {
        switch value.value {
        case let n as Int: return "\(n)"
        case let n as Double: return String(format: n.truncatingRemainder(dividingBy: 1) == 0 ? "%.0f" : "%.1f", n)
        case let s as String: return s
        default: return "\u{2014}"
        }
    }

    private func formatGeneric(_ value: AnyCodable) -> String {
        switch value.value {
        case let n as Int: return "\(n)"
        case let n as Double: return String(format: "%.1f", n)
        case let s as String: return s
        default: return "\u{2014}"
        }
    }
}
