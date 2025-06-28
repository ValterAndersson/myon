import Foundation

protocol RoutineRepositoryProtocol {
    func getRoutines(userId: String) async throws -> [Routine]
    func getRoutine(id: String, userId: String) async throws -> Routine?
    func createRoutine(_ routine: Routine) async throws -> String
    func updateRoutine(_ routine: Routine) async throws
    func deleteRoutine(id: String, userId: String) async throws
    func setActiveRoutine(routineId: String, userId: String) async throws
    func getActiveRoutine(userId: String) async throws -> Routine?
}

class RoutineRepository: RoutineRepositoryProtocol, ObservableObject {
    private let cloudService: CloudFunctionServiceProtocol
    private let firebaseService: FirebaseServiceProtocol
    
    init(
        cloudService: CloudFunctionServiceProtocol = CloudFunctionService(),
        firebaseService: FirebaseServiceProtocol = FirebaseService()
    ) {
        self.cloudService = cloudService
        self.firebaseService = firebaseService
    }
    
    func getRoutines(userId: String) async throws -> [Routine] {
        // Use cloud function for optimized queries with analytics
        do {
            return try await cloudService.getRoutines(userId: userId)
        } catch {
            // Fallback to direct Firestore query using subcollection
            return try await firebaseService.getDocumentsFromSubcollection(
                parentCollection: "users",
                parentDocumentId: userId,
                subcollection: "routines",
                query: nil
            )
        }
    }
    
    func getRoutine(id: String, userId: String) async throws -> Routine? {
        do {
            return try await cloudService.getRoutine(id: id, userId: userId)
        } catch {
            // Fallback to direct Firestore query using subcollection
            return try await firebaseService.getDocumentFromSubcollection(
                parentCollection: "users",
                parentDocumentId: userId,
                subcollection: "routines",
                documentId: id
            )
        }
    }
    
    func createRoutine(_ routine: Routine) async throws -> String {
        // Use cloud function for AI analysis and routine optimization
        do {
            return try await cloudService.createRoutine(routine: routine)
        } catch {
            // Fallback to direct Firestore creation using subcollection
            return try await firebaseService.addDocumentToSubcollection(
                parentCollection: "users",
                parentDocumentId: routine.userId,
                subcollection: "routines",
                data: routine
            )
        }
    }
    
    func updateRoutine(_ routine: Routine) async throws {
        do {
            try await cloudService.updateRoutine(id: routine.id, routine: routine)
        } catch {
            // Fallback to direct Firestore update using subcollection
            try await firebaseService.updateDocumentInSubcollection(
                parentCollection: "users",
                parentDocumentId: routine.userId,
                subcollection: "routines",
                documentId: routine.id,
                data: routine
            )
        }
    }
    
    func deleteRoutine(id: String, userId: String) async throws {
        do {
            try await cloudService.deleteRoutine(id: id, userId: userId)
        } catch {
            // Fallback to direct Firestore deletion using subcollection
            try await firebaseService.deleteDocumentFromSubcollection(
                parentCollection: "users",
                parentDocumentId: userId,
                subcollection: "routines",
                documentId: id
            )
        }
    }
    
    func setActiveRoutine(routineId: String, userId: String) async throws {
        do {
            try await cloudService.setActiveRoutine(routineId: routineId, userId: userId)
        } catch {
            // Fallback: Use cloud service as it handles the user document updates
            // For now, just log the error - we'll rely on cloud functions for user management
            print("Error setting active routine via cloud service: \(error)")
        }
    }
    
    func getActiveRoutine(userId: String) async throws -> Routine? {
        do {
            return try await cloudService.getActiveRoutine(userId: userId)
        } catch {
            // Fallback: For now, return nil - we'll rely on cloud functions for user management
            print("Error getting active routine via cloud service: \(error)")
            return nil
        }
    }
} 