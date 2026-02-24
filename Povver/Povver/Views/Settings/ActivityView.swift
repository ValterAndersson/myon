import SwiftUI

/// Activity screen — the dedicated home for agent recommendations.
/// Replaces the old RecommendationsFeedView sheet + NotificationBell overlay.
/// Auto-pilot toggle at the top controls whether recommendations require manual review.
/// autoPilotEnabled loaded from Firestore in .task, not passed as parameter, to avoid stale state.
struct ActivityView: View {
    @ObservedObject var viewModel: RecommendationsViewModel
    @ObservedObject private var authService = AuthService.shared

    @State private var autoPilotEnabled: Bool = false
    @State private var isLoadingUser: Bool = true
    @State private var isTogglingAutoPilot: Bool = false
    @State private var errorMessage: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Space.md) {
                // Auto-pilot toggle card
                autoPilotCard

                // Error banner
                if let error = errorMessage {
                    errorBanner(error)
                }

                // ViewModel-level error banner (from accept/reject actions)
                if let vmError = viewModel.errorMessage {
                    errorBanner(vmError, onDismiss: { viewModel.errorMessage = nil })
                }

                // Recommendation cards grouped by time
                if !allRecommendations.isEmpty {
                    let grouped = groupedByTime(allRecommendations)

                    if !grouped.today.isEmpty {
                        sectionHeader("Today")
                        recommendationCards(grouped.today)
                    }

                    if !grouped.thisWeek.isEmpty {
                        sectionHeader("This Week")
                        recommendationCards(grouped.thisWeek)
                    }

                    if !grouped.earlier.isEmpty {
                        sectionHeader("Earlier")
                        recommendationCards(grouped.earlier)
                    }
                } else if !isLoadingUser {
                    emptyState
                }

                Spacer(minLength: Space.xxl)
            }
            .padding(.top, Space.md)
        }
        .background(Color.bg)
        .navigationTitle("Activity")
        .navigationBarTitleDisplayMode(.inline)
        .task {
            await loadAutoPilotState()
        }
    }

    // MARK: - Auto-Pilot Card

    private var autoPilotCard: some View {
        VStack(alignment: .leading, spacing: Space.sm) {
            HStack {
                Image(systemName: "bolt.fill")
                    .font(.system(size: 18))
                    .foregroundColor(autoPilotEnabled ? Color.accent : Color.textSecondary)

                Text("Auto-Pilot")
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(Color.textPrimary)

                Spacer()

                // Toggle with optimistic update + rollback on Firestore failure.
                // isTogglingAutoPilot prevents rapid toggles from creating stale rollback values.
                Toggle("", isOn: Binding(
                    get: { autoPilotEnabled },
                    set: { newValue in
                        guard !isTogglingAutoPilot else { return }
                        let previous = autoPilotEnabled
                        autoPilotEnabled = newValue
                        errorMessage = nil
                        isTogglingAutoPilot = true
                        Task {
                            do {
                                guard let userId = authService.currentUser?.uid else { return }
                                try await UserRepository.shared.updateAutoPilot(userId: userId, enabled: newValue)
                                AnalyticsService.shared.autoPilotToggled(enabled: newValue)
                            } catch {
                                autoPilotEnabled = previous
                                errorMessage = "Failed to update. Please try again."
                            }
                            isTogglingAutoPilot = false
                        }
                    }
                ))
                .labelsHidden()
                .disabled(isLoadingUser || isTogglingAutoPilot)
            }

            Text(autoPilotEnabled
                 ? "Changes are applied automatically. You'll see a summary of what changed here."
                 : "Review each recommendation individually before it's applied.")
                .font(.system(size: 13))
                .foregroundColor(Color.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(Space.md)
        .background(Color.surface)
        .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.medium))
        .padding(.horizontal, Space.lg)
    }

    // MARK: - Recommendation Cards

    private func recommendationCards(_ recs: [AgentRecommendation]) -> some View {
        ForEach(recs) { rec in
            let isAutoApplied = rec.state == "applied" && rec.appliedBy == "agent"
            RecommendationCardView(
                recommendation: rec,
                isProcessing: viewModel.isProcessing,
                autoPilotEnabled: autoPilotEnabled && isAutoApplied,
                onAccept: rec.state == "pending_review" ? { viewModel.accept(rec) } : nil,
                onReject: rec.state == "pending_review" ? { viewModel.reject(rec) } : nil
            )
            .padding(.horizontal, Space.lg)
        }
    }

    // MARK: - Empty State

    private var emptyState: some View {
        VStack(spacing: Space.md) {
            Image(systemName: "checkmark.circle")
                .font(.system(size: 40))
                .foregroundColor(Color.textTertiary)
            Text("No activity yet")
                .font(.system(size: 16, weight: .medium))
                .foregroundColor(Color.textSecondary)
            Text("Recommendations will appear here after your workouts are analyzed.")
                .font(.system(size: 13))
                .foregroundColor(Color.textTertiary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .padding(.top, 80)
    }

    // MARK: - Error Banner

    private func errorBanner(_ message: String, onDismiss: (() -> Void)? = nil) -> some View {
        HStack {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundColor(Color.warning)
            Text(message)
                .font(.system(size: 13))
                .foregroundColor(Color.textSecondary)
            Spacer()
            if let onDismiss = onDismiss {
                Button(action: onDismiss) {
                    Image(systemName: "xmark")
                        .font(.system(size: 12))
                        .foregroundColor(Color.textTertiary)
                }
            }
        }
        .padding(Space.sm)
        .background(Color.surface)
        .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.small))
        .padding(.horizontal, Space.lg)
    }

    // MARK: - Helpers

    private var allRecommendations: [AgentRecommendation] {
        let all = viewModel.pending + viewModel.recent
        return all.sorted { $0.createdAt > $1.createdAt }
    }

    private struct TimeGrouped {
        var today: [AgentRecommendation] = []
        var thisWeek: [AgentRecommendation] = []
        var earlier: [AgentRecommendation] = []
    }

    private func groupedByTime(_ recs: [AgentRecommendation]) -> TimeGrouped {
        let calendar = Calendar.current
        let now = Date()
        let sevenDaysAgo = calendar.date(byAdding: .day, value: -7, to: now) ?? now

        var result = TimeGrouped()
        for rec in recs {
            if calendar.isDateInToday(rec.createdAt) {
                result.today.append(rec)
            } else if rec.createdAt >= sevenDaysAgo {
                result.thisWeek.append(rec)
            } else {
                result.earlier.append(rec)
            }
        }
        return result
    }

    private func sectionHeader(_ title: String) -> some View {
        Text(title.uppercased())
            .font(.system(size: 12, weight: .semibold))
            .foregroundColor(Color.textSecondary)
            .padding(.horizontal, Space.lg)
            .padding(.top, Space.sm)
    }

    private func loadAutoPilotState() async {
        guard let userId = authService.currentUser?.uid else {
            isLoadingUser = false
            return
        }
        do {
            let user = try await UserRepository.shared.getUser(userId: userId)
            autoPilotEnabled = user?.autoPilotEnabled ?? false
        } catch {
            // Defaults to false, which is safe
        }
        isLoadingUser = false
        AnalyticsService.shared.activityViewed(pendingCount: viewModel.pendingCount)
    }
}
