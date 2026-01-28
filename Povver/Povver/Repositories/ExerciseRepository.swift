import Foundation
import FirebaseFirestore

class ExerciseRepository: FirestoreRepository<Exercise> {
    init() {
        super.init(collection: Firestore.firestore().collection("exercises"))
    }

    /// Override list() to add error logging and manual ID injection
    override func list() async throws -> [Exercise] {
        let snapshot = try await collection.getDocuments()
        print("[ExerciseRepository] Fetched \(snapshot.documents.count) documents from Firestore")

        var exercises: [Exercise] = []
        var errorCount = 0

        for document in snapshot.documents {
            do {
                var exercise = try document.data(as: Exercise.self)
                // Manually inject document ID since @DocumentID may not work with custom init
                if exercise.id == nil {
                    exercise.id = document.documentID
                }
                exercises.append(exercise)
            } catch {
                errorCount += 1
                if errorCount <= 5 {
                    print("[ExerciseRepository] Failed to decode \(document.documentID): \(error)")
                }
            }
        }

        if errorCount > 0 {
            print("[ExerciseRepository] Total decode errors: \(errorCount) / \(snapshot.documents.count)")
        }
        print("[ExerciseRepository] Successfully decoded \(exercises.count) exercises")

        return exercises
    }

    /// Override read() to add manual ID injection
    override func read(id: String) async throws -> Exercise? {
        let document = try await collection.document(id).getDocument()
        guard document.exists else { return nil }

        do {
            var exercise = try document.data(as: Exercise.self)
            if exercise.id == nil {
                exercise.id = document.documentID
            }
            return exercise
        } catch {
            print("[ExerciseRepository] Failed to decode \(id): \(error)")
            throw error
        }
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
