import Foundation

protocol TemplateRepositoryProtocol {
    func getTemplates(userId: String) async throws -> [WorkoutTemplate]
    func getTemplate(id: String, userId: String) async throws -> WorkoutTemplate?
    func createTemplate(_ template: WorkoutTemplate) async throws -> String
    func updateTemplate(_ template: WorkoutTemplate) async throws
    func deleteTemplate(id: String, userId: String) async throws
}

class TemplateRepository: TemplateRepositoryProtocol, ObservableObject {
    private let cloudService: CloudFunctionServiceProtocol
    private let firebaseService: FirebaseServiceProtocol
    
    init(
        cloudService: CloudFunctionServiceProtocol = CloudFunctionService(),
        firebaseService: FirebaseServiceProtocol = FirebaseService()
    ) {
        self.cloudService = cloudService
        self.firebaseService = firebaseService
    }
    
    func getTemplates(userId: String) async throws -> [WorkoutTemplate] {
        // Use cloud function for optimized queries and potential AI filtering
        do {
            return try await cloudService.getTemplates(userId: userId)
        } catch {
            // Fallback to direct Firestore query using subcollection
            return try await firebaseService.getDocumentsFromSubcollection(
                parentCollection: "users",
                parentDocumentId: userId,
                subcollection: "templates",
                query: nil
            )
        }
    }
    
    func getTemplate(id: String, userId: String) async throws -> WorkoutTemplate? {
        do {
            return try await cloudService.getTemplate(id: id, userId: userId)
        } catch {
            // Fallback to direct Firestore query using subcollection
            return try await firebaseService.getDocumentFromSubcollection(
                parentCollection: "users",
                parentDocumentId: userId,
                subcollection: "templates",
                documentId: id
            )
        }
    }
    
    func createTemplate(_ template: WorkoutTemplate) async throws -> String {
        // Use cloud function for AI analysis and intelligent categorization
        do {
            return try await cloudService.createTemplate(template: template)
        } catch {
            // Fallback to direct Firestore creation using subcollection
            return try await firebaseService.addDocumentToSubcollection(
                parentCollection: "users",
                parentDocumentId: template.userId,
                subcollection: "templates",
                data: template
            )
        }
    }
    
    func updateTemplate(_ template: WorkoutTemplate) async throws {
        do {
            try await cloudService.updateTemplate(id: template.id, template: template)
        } catch {
            // Fallback to direct Firestore update using subcollection
            try await firebaseService.updateDocumentInSubcollection(
                parentCollection: "users",
                parentDocumentId: template.userId,
                subcollection: "templates",
                documentId: template.id,
                data: template
            )
        }
    }
    
    func deleteTemplate(id: String, userId: String) async throws {
        do {
            try await cloudService.deleteTemplate(id: id, userId: userId)
        } catch {
            // Fallback to direct Firestore deletion using subcollection
            try await firebaseService.deleteDocumentFromSubcollection(
                parentCollection: "users",
                parentDocumentId: userId,
                subcollection: "templates",
                documentId: id
            )
        }
        
        // Clean up any routine references to this template
        try await removeTemplateFromRoutines(templateId: id, userId: userId)
    }
    
    // MARK: - Cascade Operations
    private func removeTemplateFromRoutines(templateId: String, userId: String) async throws {
        // Get all routines for this user
        let routineRepository = RoutineRepository()
        let routines = try await routineRepository.getRoutines(userId: userId)
        
        // Find routines that reference this template and update them
        for routine in routines {
            if routine.templateIds.contains(templateId) {
                var updatedRoutine = routine
                updatedRoutine.templateIds.removeAll { $0 == templateId }
                updatedRoutine.updatedAt = Date()
                
                // Update the routine
                try await routineRepository.updateRoutine(updatedRoutine)
            }
        }
    }
}

