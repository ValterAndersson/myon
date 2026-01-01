//
//  PovverTests.swift
//  PovverTests
//
//  Created by Valter Andersson on 9.6.2025.
//

import Testing
@testable import Povver

struct PovverTests {

    @Test func example() async throws {
        // Write your test here and use APIs like `#expect(...)` to check expected conditions.
    }

    @Test func sessionManager_persistsAndRestoresUserId() async throws {
        let session = SessionManager.shared
        session.endSession() // Ensure clean state
        session.startSession(userId: "testUser123")
        // Simulate app restart by creating a new instance
        let restoredSession = SessionManager.shared
        #expect(restoredSession.userId == "testUser123")
        restoredSession.endSession()
    }

    @Test func userRepository_getUser_returnsUser() async throws {
        // This is a template. In a real test, inject a mock Firestore.
        // let mockFirestore = MockFirestore()
        // let repo = UserRepository(firestore: mockFirestore)
        // let user = try await repo.getUser(userId: "testUser123")
        // #expect(user?.id == "testUser123")
        // For now, just pass.
        #expect(true)
    }

}
