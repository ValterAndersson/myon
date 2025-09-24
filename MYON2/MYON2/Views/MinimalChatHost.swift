import SwiftUI
import UIKit

struct MinimalChatHost: View {
    @State private var session: ChatSession?
    @State private var isLoading = false
    @State private var errorMessage: String?
    
    var body: some View {
        Group {
            if let session = session {
                ChatViewRepresentable(session: session)
                    .ignoresSafeArea(.keyboard)
            } else if isLoading {
                ProgressView("Starting chat…")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let errorMessage = errorMessage {
                VStack(spacing: 12) {
                    Text("Failed to start chat")
                        .font(.headline)
                    Text(errorMessage)
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                    Button("Retry") { createSession() }
                }
                .padding()
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                // Idle state (first launch)
                VStack(spacing: 12) {
                    Button("Start New Chat") { createSession() }
                        .buttonStyle(.borderedProminent)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .onAppear {
            if session == nil && !isLoading { createSession() }
        }
        .navigationTitle("")
        .navigationBarTitleDisplayMode(.inline)
    }
    
    private func createSession() {
        isLoading = true
        errorMessage = nil
        Task {
            do {
                let newSession = try await ChatService.shared.createNewSession()
                await MainActor.run {
                    self.session = newSession
                    self.isLoading = false
                }
            } catch {
                await MainActor.run {
                    self.errorMessage = error.localizedDescription
                    self.isLoading = false
                }
            }
        }
    }
}

// MARK: - UIKit Bridge
struct ChatViewRepresentable: UIViewControllerRepresentable {
    let session: ChatSession
    
    func makeUIViewController(context: Context) -> ChatViewController {
        let vc = ChatViewController()
        vc.isEmbedded = true
        vc.session = session
        return vc
    }
    
    func updateUIViewController(_ uiViewController: ChatViewController, context: Context) {
        // If session changed, update and reload messages
        if uiViewController.session?.id != session.id {
            uiViewController.session = session
            uiViewController.loadSessionMessages()
        }
    }
}


