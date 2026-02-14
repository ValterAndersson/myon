import SwiftUI

/// Compact chat view for mid-workout coaching.
/// Design principles:
/// - Large text (readable at arm's length on a bench)
/// - Big send button (sweaty fingers)
/// - Minimal chrome — no avatars, no timestamps
/// - Auto-scroll to latest message
struct WorkoutCoachView: View {
    @ObservedObject var viewModel: WorkoutCoachViewModel
    @FocusState private var isInputFocused: Bool

    var body: some View {
        VStack(spacing: 0) {
            // Header
            header

            Divider()

            // Messages
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(spacing: Space.md) {
                        ForEach(viewModel.messages) { message in
                            messageBubble(message)
                                .id(message.id)
                        }

                        if viewModel.messages.isEmpty {
                            emptyState
                        }
                    }
                    .padding(.horizontal, Space.md)
                    .padding(.vertical, Space.md)
                }
                .onChange(of: viewModel.messages.count) { _, _ in
                    if let last = viewModel.messages.last {
                        withAnimation(.easeOut(duration: 0.2)) {
                            proxy.scrollTo(last.id, anchor: .bottom)
                        }
                    }
                }
            }

            Divider()

            // Input bar
            inputBar
        }
        .background(Color.bg)
    }

    private var header: some View {
        HStack {
            Image(systemName: "sparkles")
                .font(.system(size: 16, weight: .medium))
                .foregroundColor(Color.accent)

            Text("Coach")
                .font(.system(size: 17, weight: .semibold))
                .foregroundColor(Color.textPrimary)

            Spacer()
        }
        .padding(.horizontal, Space.lg)
        .padding(.vertical, Space.md)
    }

    @ViewBuilder
    private func messageBubble(_ message: ChatMessage) -> some View {
        HStack {
            if message.author == .user {
                Spacer(minLength: 60)
            }

            Text(message.content.displayText)
                .font(.system(size: 17))
                .foregroundColor(message.author == .user ? .textInverse : Color.textPrimary)
                .padding(.horizontal, 16)
                .padding(.vertical, 12)
                .background(
                    message.author == .user
                        ? Color.accent
                        : Color.surface
                )
                .clipShape(RoundedRectangle(cornerRadius: 18))
                .overlay(
                    Group {
                        if message.status == .streaming {
                            RoundedRectangle(cornerRadius: 18)
                                .stroke(Color.accent.opacity(0.3), lineWidth: 1)
                        }
                    }
                )

            if message.author != .user {
                Spacer(minLength: 60)
            }
        }
    }

    private var emptyState: some View {
        VStack(spacing: Space.md) {
            Spacer(minLength: 40)

            Image(systemName: "sparkles")
                .font(.system(size: 32))
                .foregroundColor(Color.accent.opacity(0.5))

            Text("Ask me anything")
                .font(.system(size: 15))
                .foregroundColor(Color.textSecondary)

            VStack(spacing: Space.sm) {
                suggestionChip("What weight next?")
                suggestionChip("How's my bench going?")
                suggestionChip("Swap to dumbbells")
            }

            Spacer()
        }
    }

    private func suggestionChip(_ text: String) -> some View {
        Button {
            viewModel.inputText = text
            Task { await viewModel.send() }
        } label: {
            Text(text)
                .font(.system(size: 14, weight: .medium))
                .foregroundColor(Color.accent)
                .padding(.horizontal, 14)
                .padding(.vertical, 8)
                .background(Color.accentMuted)
                .clipShape(Capsule())
        }
        .buttonStyle(PlainButtonStyle())
    }

    private var inputBar: some View {
        HStack(spacing: Space.sm) {
            TextField("Ask your coach...", text: $viewModel.inputText)
                .font(.system(size: 17))
                .padding(.horizontal, 16)
                .padding(.vertical, 12)
                .background(Color.surface)
                .clipShape(RoundedRectangle(cornerRadius: 22))
                .focused($isInputFocused)
                .submitLabel(.send)
                .onSubmit {
                    Task { await viewModel.send() }
                }

            // Send button - large for sweaty fingers
            Button {
                Task { await viewModel.send() }
            } label: {
                Image(systemName: viewModel.isStreaming ? "stop.circle.fill" : "arrow.up.circle.fill")
                    .font(.system(size: 36))
                    .foregroundColor(
                        viewModel.inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !viewModel.isStreaming
                            ? Color.textTertiary
                            : Color.accent
                    )
            }
            .buttonStyle(PlainButtonStyle())
            .disabled(viewModel.inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !viewModel.isStreaming)
        }
        .padding(.horizontal, Space.md)
        .padding(.vertical, Space.sm)
        .background(Color.bg)
    }
}
