import SwiftUI

struct RecommendationsFeedView: View {
    @ObservedObject var viewModel: RecommendationsViewModel
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: Space.md) {
                    // Error banner
                    if let error = viewModel.errorMessage {
                        HStack {
                            Image(systemName: "exclamationmark.triangle.fill")
                                .foregroundColor(.orange)
                            Text(error)
                                .font(.system(size: 13))
                                .foregroundColor(Color.textSecondary)
                            Spacer()
                            Button { viewModel.errorMessage = nil } label: {
                                Image(systemName: "xmark")
                                    .font(.system(size: 12))
                                    .foregroundColor(Color.textTertiary)
                            }
                        }
                        .padding(Space.sm)
                        .background(Color.surface)
                        .clipShape(RoundedRectangle(cornerRadius: CornerRadiusToken.small))
                        .padding(.horizontal, Space.lg)
                    }

                    // Pending section
                    if !viewModel.pending.isEmpty {
                        sectionHeader("Pending Review")
                        ForEach(viewModel.pending) { rec in
                            RecommendationCardView(
                                recommendation: rec,
                                isProcessing: viewModel.isProcessing,
                                onAccept: { viewModel.accept(rec) },
                                onReject: { viewModel.reject(rec) }
                            )
                            .padding(.horizontal, Space.lg)
                        }
                    }

                    // Recent section
                    if !viewModel.recent.isEmpty {
                        sectionHeader("Recent")
                        ForEach(viewModel.recent) { rec in
                            RecommendationCardView(
                                recommendation: rec,
                                isProcessing: false
                            )
                            .padding(.horizontal, Space.lg)
                        }
                    }

                    // Empty state
                    if viewModel.pending.isEmpty && viewModel.recent.isEmpty {
                        VStack(spacing: Space.md) {
                            Image(systemName: "checkmark.circle")
                                .font(.system(size: 40))
                                .foregroundColor(Color.textTertiary)
                            Text("No recommendations")
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

                    Spacer(minLength: Space.xxl)
                }
                .padding(.top, Space.md)
            }
            .background(Color.bg)
            .navigationTitle("Recommendations")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }

    private func sectionHeader(_ title: String) -> some View {
        Text(title.uppercased())
            .font(.system(size: 12, weight: .semibold))
            .foregroundColor(Color.textSecondary)
            .padding(.horizontal, Space.lg)
            .padding(.top, Space.sm)
    }
}
