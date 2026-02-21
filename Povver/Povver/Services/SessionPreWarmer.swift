import Foundation
import SwiftUI

/**
 =============================================================================
 SessionPreWarmer.swift - Background Session Pre-Warming
 =============================================================================
 
 PURPOSE:
 Pre-warms Vertex AI Agent Engine sessions in the background to eliminate
 the ~2-3 second cold start latency when opening a canvas.
 
 ARCHITECTURE:
 ┌─────────────────┐       ┌─────────────────────────────┐       ┌────────────────────┐
 │ ChatHomeView    │       │ SessionPreWarmer            │       │ Firebase           │
 │                 │       │                             │       │                    │
 │ .onAppear ──────┼──────►│ preWarmIfNeeded()           │       │ preWarmSession     │
 │                 │       │   │                         │──────►│ open-canvas.js     │
 │                 │       │   ├─ debounce check         │       │                    │
 │                 │       │   ├─ call backend           │◄──────│ Returns:           │
 │                 │       │   └─ cache result           │       │ - canvasId         │
 │                 │       │                             │       │ - sessionId        │
 │ CanvasScreen    │       │ getPreWarmedSession()       │       │                    │
 │ .onAppear ──────┼──────►│   └─ return cached result   │       │                    │
 └─────────────────┘       └─────────────────────────────┘       └────────────────────┘
 
 HOW IT WORKS:
 1. When user lands on ChatHomeView, `preWarmIfNeeded()` is called
 2. Backend creates/reuses Vertex AI session + canvas (takes ~2-3s for new)
 3. Result is cached in memory with timestamp
 4. When user opens CanvasScreen, `openCanvas` finds the warm session in Firestore
 5. Canvas opens instantly (~300ms) instead of waiting for session creation
 
 LOGGING:
 All pre-warm operations are logged via SessionLogger for debugging:
 - Pre-warm start with trigger source
 - Pre-warm success with canvas/session IDs and duration
 - Pre-warm failures with error details
 - Session consumption (when pre-warmed session is used)
 
 RELATED FILES:
 - CanvasService.swift: preWarmSession() HTTP call
 - ChatHomeView.swift: Triggers pre-warm on appear
 - CanvasViewModel.swift: Consumes pre-warmed session via openCanvas
 - open-canvas.js: Backend implementation
 
 =============================================================================
 */

/// Represents a pre-warmed session that's ready to use
struct PreWarmedSession {
    let canvasId: String
    let sessionId: String
    let purpose: String
    let userId: String
    let createdAt: Date
    let isNew: Bool
    
    var ageMs: Int {
        Int(Date().timeIntervalSince(createdAt) * 1000)
    }
    
    /// Sessions are considered stale after 15 minutes in cache
    /// (The actual session TTL is 55 min in Firestore, Vertex AI ~60 min)
    var isStale: Bool {
        ageMs > 15 * 60 * 1000
    }
}

/// Singleton service to manage session pre-warming
@MainActor
final class SessionPreWarmer: ObservableObject {
    static let shared = SessionPreWarmer()
    
    /// The current pre-warmed session (if any)
    @Published private(set) var preWarmedSession: PreWarmedSession?
    
    /// Whether a pre-warm is currently in progress
    @Published private(set) var isPreWarming: Bool = false
    
    /// Last error from pre-warming (for debugging)
    @Published private(set) var lastError: Error?
    
    private let canvasService = CanvasService()
    
    /// Minimum time between pre-warm attempts (debounce)
    private let debounceInterval: TimeInterval = 10.0 // 10 seconds
    private var lastPreWarmAttempt: Date?
    
    /// Task handle for cancellation
    private var preWarmTask: Task<Void, Never>?
    
    private init() {}
    
    // MARK: - Public API
    
    /// Pre-warm a session if needed. Called when user lands on homepage.
    /// 
    /// This is debounced to prevent excessive calls if user navigates quickly.
    /// - Parameters:
    ///   - userId: Current user ID
    ///   - purpose: Session purpose (default: "ad_hoc")
    ///   - trigger: What triggered this pre-warm (for logging)
    func preWarmIfNeeded(userId: String, purpose: String = "ad_hoc", trigger: String = "unknown") {
        // Skip if already pre-warming
        guard !isPreWarming else {
            AppLogger.shared.info(.app, "pre-warm SKIPPED (already in progress)")
            return
        }

        // Skip if we already have a valid pre-warmed session for this user/purpose
        if let existing = preWarmedSession,
           existing.userId == userId,
           existing.purpose == purpose,
           !existing.isStale {
            AppLogger.shared.info(.app, "pre-warm SKIPPED (cached valid age=\(existing.ageMs)ms)")
            return
        }

        // Debounce: skip if we attempted recently
        if let lastAttempt = lastPreWarmAttempt,
           Date().timeIntervalSince(lastAttempt) < debounceInterval {
            AppLogger.shared.info(.app, "pre-warm DEBOUNCED (\(Int(Date().timeIntervalSince(lastAttempt)))s since last)")
            return
        }
        
        // Start pre-warming
        lastPreWarmAttempt = Date()
        preWarmTask?.cancel()
        preWarmTask = Task {
            await performPreWarm(userId: userId, purpose: purpose, trigger: trigger)
        }
    }
    
    /// Get the current pre-warmed session if valid, and mark it as consumed.
    /// 
    /// Returns nil if no valid pre-warmed session exists.
    /// After consumption, the session is cleared from cache.
    func consumePreWarmedSession(userId: String, purpose: String = "ad_hoc") -> PreWarmedSession? {
        guard let session = preWarmedSession,
              session.userId == userId,
              session.purpose == purpose,
              !session.isStale else {

            if let existing = preWarmedSession {
                let reason = existing.isStale ? "stale" : "mismatch"
                AppLogger.shared.info(.app, "pre-warmed session NOT consumed (\(reason))")
            }
            return nil
        }

        // Log consumption
        AppLogger.shared.info(.app, "CONSUMING pre-warmed session age=\(session.ageMs)ms")
        
        // Clear the cache (session can only be consumed once)
        preWarmedSession = nil
        
        return session
    }
    
    /// Cancel any in-progress pre-warming
    func cancel() {
        preWarmTask?.cancel()
        preWarmTask = nil
        isPreWarming = false
    }
    
    /// Clear the cached pre-warmed session
    func clearCache() {
        preWarmedSession = nil
        lastError = nil
    }
    
    // MARK: - Private Implementation
    
    private func performPreWarm(userId: String, purpose: String, trigger: String) async {
        let startTime = Date()
        
        isPreWarming = true
        lastError = nil

        AppLogger.shared.info(.app, "pre-warm START trigger=\(trigger)")

        do {
            // Call the backend to create/reuse session
            let sessionId = try await canvasService.preWarmSession(userId: userId, purpose: purpose)

            let durationMs = Int(Date().timeIntervalSince(startTime) * 1000)

            AppLogger.shared.info(.app, "pre-warm SUCCESS \(durationMs)ms session=\(sessionId.prefix(8))")

            // Cache the result
            // Note: We don't have canvasId from preWarmSession - openCanvas will find it
            // The session is stored in Firestore, so openCanvas will reuse it
            preWarmedSession = PreWarmedSession(
                canvasId: "pending",  // Will be resolved by openCanvas
                sessionId: sessionId,
                purpose: purpose,
                userId: userId,
                createdAt: Date(),
                isNew: true  // We don't know from current API
            )

        } catch {
            let durationMs = Int(Date().timeIntervalSince(startTime) * 1000)

            AppLogger.shared.error(.app, "pre-warm FAILED \(durationMs)ms", error)

            lastError = error
        }
        
        isPreWarming = false
    }
}

// MARK: - Convenience extension for SwiftUI

extension View {
    /// Trigger session pre-warming when this view appears.
    /// 
    /// Usage:
    /// ```swift
    /// MyView()
    ///     .preWarmSession(userId: userId, trigger: "homepage")
    /// ```
    func preWarmSession(userId: String, purpose: String = "ad_hoc", trigger: String = "view_appear") -> some View {
        self.onAppear {
            Task { @MainActor in
                SessionPreWarmer.shared.preWarmIfNeeded(userId: userId, purpose: purpose, trigger: trigger)
            }
        }
    }
}
