import Foundation
import Foundation

/// Test class for validating DirectStreamingService
@MainActor
class DirectStreamingTest {
    static let shared = DirectStreamingTest()
    
    private let streamingService = DirectStreamingService()
    
    private init() {}
    
    /// Run comprehensive tests of the direct streaming service
    func runTests() async {
#if DEBUG
        print("🧪 Starting Direct Streaming Tests...")
        
        guard let userId = AuthService.shared.currentUser?.uid else {
            print("❌ No authenticated user")
            return
        }
        
        print("✅ User ID: \(userId)")
        
        do {
            // Test 1: Create Session
            print("\n1️⃣ Testing session creation...")
            let sessionId = try await streamingService.createSession(userId: userId)
            print("✅ Session created: \(sessionId)")
            
            // Test 2: List Sessions
            print("\n2️⃣ Testing list sessions...")
            let sessions = try await streamingService.listSessions(userId: userId)
            print("✅ Found \(sessions.count) sessions")
            if sessions.contains(sessionId) {
                print("✅ Newly created session is in the list")
            } else {
                print("❌ Newly created session not found in list")
            }
            
            // Test 3: Stream Query
            print("\n3️⃣ Testing streaming query...")
            await testStreamingQuery(sessionId: sessionId, userId: userId, message: "Can you analyze my last workout?")
            
            // Wait a bit
            try await Task.sleep(nanoseconds: 2_000_000_000) // 2 seconds
            
            // Test 4: Context Persistence
            print("\n4️⃣ Testing context persistence...")
            await testStreamingQuery(sessionId: sessionId, userId: userId, message: "What specific improvements would you suggest?")
            
            // Test 5: Delete Session
            print("\n5️⃣ Testing session deletion...")
            try await streamingService.deleteSession(sessionId: sessionId, userId: userId)
            print("✅ Session deleted")
            
            // Verify deletion
            let sessionsAfterDelete = try await streamingService.listSessions(userId: userId)
            if !sessionsAfterDelete.contains(sessionId) {
                print("✅ Session successfully removed from list")
            } else {
                print("❌ Session still exists after deletion")
            }
            
            print("\n✅ All tests completed successfully!")
            
        } catch {
            print("\n❌ Test failed with error: \(error.localizedDescription)")
    }
#else
        // Disabled outside DEBUG
        return
#endif
    }
    
    private func testStreamingQuery(sessionId: String, userId: String, message: String) async {
        return await withCheckedContinuation { continuation in
            var eventCount = 0
            
            streamingService.streamQuery(
                message: message,
                userId: userId,
                sessionId: sessionId,
                progressHandler: { partialText, action in
                    if let action = action {
                        print("  ⚙️  Action: \(action)")
                        return
                    }
                    if let partialText = partialText {
                        eventCount += 1
                        print("  📊 Streaming update \(eventCount): \(partialText.count) chars", terminator: "\r")
                        fflush(stdout)
                    }
                },
                completion: { result in
                    switch result {
                    case .success(let (response, returnedSessionId)):
                        print("\n  ✅ Response received (\(eventCount) streaming events)")
                        print("  📝 Final response length: \(response.count) chars")
                        if let returnedSessionId = returnedSessionId {
                            print("  🔑 Session ID: \(returnedSessionId)")
                        }
                        // Print first 200 chars of response
                        let preview = String(response.prefix(200))
                        print("  💬 Response preview: \(preview)...")
                        
                    case .failure(let error):
                        print("\n  ❌ Stream failed: \(error.localizedDescription)")
                    }
                    
                    continuation.resume()
                }
            )
        }
    }

}

// Extension to add this test to the app
// UI extension removed to decouple from presentation layer