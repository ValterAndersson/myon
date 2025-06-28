import SwiftUI
import UIKit

struct StrengthOSView: View {
    @State private var currentSession: ChatSession?
    @State private var sessions: [ChatSession] = []
    @State private var isLoadingSessions = true
    @State private var showingSessionDrawer = false
    @State private var errorMessage: String?
    @State private var showingError = false
    
    private let chatService = ChatService.shared
    
    var body: some View {
        NavigationView {
            ZStack {
                if let session = currentSession {
                    // Show chat interface
                    ChatViewControllerRepresentable(session: session)
                        .ignoresSafeArea(edges: .bottom)
                } else if isLoadingSessions {
                    // Show loading state
                    ProgressView("Loading sessions...")
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                    // Show empty state
                    EmptyStateView(onStartChat: startNewChat)
                }
            }
            .navigationTitle("StrengthOS")
            .navigationBarTitleDisplayMode(.large)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    if !sessions.isEmpty || currentSession != nil {
                        Button(action: { showingSessionDrawer = true }) {
                            Image(systemName: "clock.arrow.circlepath")
                        }
                    }
                }
            }
        }
        .sheet(isPresented: $showingSessionDrawer) {
            SessionDrawerView(
                sessions: $sessions,
                currentSession: $currentSession,
                onNewSession: startNewChat,
                onDeleteSession: deleteSession
            )
        }
        .alert("Error", isPresented: $showingError) {
            Button("OK") { }
        } message: {
            Text(errorMessage ?? "An error occurred")
        }
        .onAppear {
            // Give Firebase Auth a moment to initialize
            Task {
                try? await Task.sleep(nanoseconds: 500_000_000) // 0.5 seconds
                loadSessions()
            }
            
            // Listen for session updates from ADK
            NotificationCenter.default.addObserver(
                forName: Notification.Name("SessionUpdated"),
                object: nil,
                queue: .main
            ) { notification in
                if let updatedSession = notification.userInfo?["session"] as? ChatSession {
                    // Update the session in our list
                    if let index = sessions.firstIndex(where: { $0.id == currentSession?.id }) {
                        sessions[index] = updatedSession
                    }
                    currentSession = updatedSession
                }
            }
        }
    }
    
    private func loadSessions() {
        Task {
            do {
                // Debug: Check authentication state
                if let user = AuthService.shared.currentUser {
                    print("✅ User is authenticated: \(user.uid)")
                } else {
                    print("❌ No user is authenticated")
                }
                
                isLoadingSessions = true
                
                // Fetch sessions via ChatService which talks to DirectStreamingService
                sessions = try await chatService.loadSessions()
                
                // If there's at least one session and none is selected, pick the most recent
                if currentSession == nil {
                    currentSession = sessions.first
                }
                
                isLoadingSessions = false
            } catch {
                print("Failed to load sessions: \(error)")
                isLoadingSessions = false
                
                // If it's an auth error, we might just not have sessions yet
                if case StrengthOSError.notAuthenticated = error {
                    // User needs to sign in first
                    errorMessage = "Please sign in to use StrengthOS"
                    showingError = true
                } else {
                    // For other errors, we can still show the empty state
                    // and let the user create a new session
                    print("Non-critical error loading sessions, showing empty state")
                }
            }
        }
    }
    
    private func startNewChat() {
        Task {
            do {
                let newSession = try await chatService.createNewSession()
                
                // Add to sessions list
                sessions.insert(newSession, at: 0)
                
                // Set as current session
                currentSession = newSession
                showingSessionDrawer = false
            } catch {
                errorMessage = error.localizedDescription
                showingError = true
            }
        }
    }
    
    private func deleteSession(_ session: ChatSession) {
        Task {
            do {
                // Attempt remote deletion via ChatService
                try await chatService.deleteSession(session.id)
            } catch {
                print("Failed to delete session remotely: \(error)")
            }
            
            // Remove from local list regardless of remote result to keep UI responsive
            sessions.removeAll { $0.id == session.id }
            
            // If we deleted the current session, clear it
            if currentSession?.id == session.id {
                currentSession = sessions.first
            }
        }
    }
}

// MARK: - Empty State View
struct EmptyStateView: View {
    let onStartChat: () -> Void
    
    var body: some View {
        VStack(spacing: 24) {
            Spacer()
            
            // Icon
            Image(systemName: "brain")
                .font(.system(size: 80))
                .foregroundColor(.blue)
                .padding(.bottom, 8)
            
            // Title
            Text("Welcome to StrengthOS")
                .font(.title2)
                .fontWeight(.bold)
            
            // Description
            Text("Your AI-powered fitness coach is ready to help you achieve your goals")
                .font(.body)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 40)
            
            // Start button
            Button(action: onStartChat) {
                HStack {
                    Image(systemName: "message.fill")
                    Text("Start New Chat")
                }
                .font(.headline)
                .foregroundColor(.white)
                .padding(.horizontal, 24)
                .padding(.vertical, 12)
                .background(Color.blue)
                .cornerRadius(25)
            }
            .padding(.top, 8)
            
            Spacer()
            Spacer()
        }
    }
}

// MARK: - UIKit Bridge for ChatViewController
struct ChatViewControllerRepresentable: UIViewControllerRepresentable {
    let session: ChatSession
    
    func makeUIViewController(context: Context) -> UINavigationController {
        let chatVC = ChatViewController()
        chatVC.session = session
        chatVC.isEmbedded = true // Flag to know it's embedded, not modal
        
        let navController = UINavigationController(rootViewController: chatVC)
        navController.isNavigationBarHidden = true // We're using SwiftUI navigation
        
        return navController
    }
    
    func updateUIViewController(_ uiViewController: UINavigationController, context: Context) {
        if let chatVC = uiViewController.viewControllers.first as? ChatViewController {
            // Check if session actually changed
            if chatVC.session?.id != session.id {
                chatVC.session = session
                // Reload messages for the new session
                chatVC.loadSessionMessages()
            }
        }
    }
}

// MARK: - Session Drawer (SwiftUI version)
struct SessionDrawerView: View {
    @Binding var sessions: [ChatSession]
    @Binding var currentSession: ChatSession?
    let onNewSession: () -> Void
    let onDeleteSession: (ChatSession) -> Void
    @Environment(\.dismiss) var dismiss
    
    var body: some View {
        NavigationView {
            List {
                Section {
                    Button(action: {
                        onNewSession()
                        dismiss()
                    }) {
                        HStack {
                            Image(systemName: "plus.circle.fill")
                                .foregroundColor(.blue)
                            Text("New Chat")
                                .foregroundColor(.primary)
                        }
                    }
                }
                
                if !sessions.isEmpty {
                    Section("Recent Chats") {
                        ForEach(sessions) { session in
                            SessionRow(session: session, isSelected: session.id == currentSession?.id)
                                .onTapGesture {
                                    currentSession = session
                                    dismiss()
                                }
                        }
                        .onDelete(perform: deleteSessions)
                    }
                }
            }
            .navigationTitle("Chat Sessions")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Done") {
                        dismiss()
                    }
                }
            }
        }
    }
    
    private func deleteSessions(at offsets: IndexSet) {
        for index in offsets {
            let session = sessions[index]
            onDeleteSession(session)
        }
    }
}

// MARK: - Session Row
struct SessionRow: View {
    let session: ChatSession
    let isSelected: Bool
    
    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                Text(session.title)
                    .font(.headline)
                    .lineLimit(1)
                
                if let lastMessage = session.lastMessage {
                    Text(lastMessage)
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                        .lineLimit(2)
                }
                
                HStack {
                    if session.messageCount > 0 {
                        Text("\(session.messageCount) message\(session.messageCount == 1 ? "" : "s")")
                    } else {
                        Text("No messages")
                    }
                    Text("•")
                    Text(session.lastUpdated.relativeTimeString())
                }
                .font(.caption)
                .foregroundColor(.secondary)
            }
            
            Spacer()
            
            if isSelected {
                Image(systemName: "checkmark.circle.fill")
                    .foregroundColor(.blue)
            }
        }
        .padding(.vertical, 4)
    }
} 