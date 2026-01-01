import Foundation
import FirebaseFirestore

class ExerciseRepository: FirestoreRepository<Exercise> {
    init() {
        super.init(collection: Firestore.firestore().collection("exercises"))
    }
    
    func getExercisesByCategory(_ category: String) async throws -> [Exercise] {
        let snapshot = try await collection
            .whereField("category", isEqualTo: category)
            .getDocuments()
        return try snapshot.documents.compactMap { try $0.data(as: Exercise.self) }
    }
    
    func getExercisesByMovementType(_ type: String) async throws -> [Exercise] {
        let snapshot = try await collection
            .whereField("movement.type", isEqualTo: type)
            .getDocuments()
        return try snapshot.documents.compactMap { try $0.data(as: Exercise.self) }
    }
    
    func getExercisesByLevel(_ level: String) async throws -> [Exercise] {
        let snapshot = try await collection
            .whereField("metadata.level", isEqualTo: level)
            .getDocuments()
        return try snapshot.documents.compactMap { try $0.data(as: Exercise.self) }
    }
    
    func searchExercises(query: String) async throws -> [Exercise] {
        // Simple client-side search - get all exercises and filter
        let allExercises = try await list()
        
        let searchTerm = query.lowercased()
        return allExercises.filter { exercise in
            let searchableText = [
                exercise.name,
                exercise.category,
                exercise.movementType,
                exercise.level,
                exercise.equipment.joined(separator: " "),
                exercise.primaryMuscles.joined(separator: " "),
                exercise.secondaryMuscles.joined(separator: " ")
            ].joined(separator: " ").lowercased()
            
            return searchableText.contains(searchTerm)
        }
    }
    
    func getExercisesByPrimaryMuscle(_ muscle: String) async throws -> [Exercise] {
        let snapshot = try await collection
            .whereField("muscles.primary", arrayContains: muscle)
            .getDocuments()
        return try snapshot.documents.compactMap { try $0.data(as: Exercise.self) }
    }
    
    func getExercisesBySecondaryMuscle(_ muscle: String) async throws -> [Exercise] {
        let snapshot = try await collection
            .whereField("muscles.secondary", arrayContains: muscle)
            .getDocuments()
        return try snapshot.documents.compactMap { try $0.data(as: Exercise.self) }
    }
    
    func getExercisesByEquipment(_ equipment: String) async throws -> [Exercise] {
        let snapshot = try await collection
            .whereField("equipment", arrayContains: equipment)
            .getDocuments()
        return try snapshot.documents.compactMap { try $0.data(as: Exercise.self) }
    }
} 
