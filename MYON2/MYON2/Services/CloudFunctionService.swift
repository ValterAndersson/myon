import Foundation
import FirebaseFunctions
// Archived path: Prefer direct HTTP via ApiClient for onRequest endpoints.
// Keeping limited callable use for legacy features only.

protocol CloudFunctionServiceProtocol {
    // Exercise operations
    func getExercises() async throws -> [Exercise]
    func getExercise(id: String) async throws -> Exercise
    
    // User operations
    func getUser(userId: String) async throws -> User
    func updateUser(userId: String, user: User) async throws
    
    // Template operations
    func getTemplates(userId: String) async throws -> [WorkoutTemplate]
    func getTemplate(id: String, userId: String) async throws -> WorkoutTemplate
    func createTemplate(template: WorkoutTemplate) async throws -> String
    func updateTemplate(id: String, template: WorkoutTemplate) async throws
    func deleteTemplate(id: String, userId: String) async throws
    
    // Routine operations
    func getRoutines(userId: String) async throws -> [Routine]
    func getRoutine(id: String, userId: String) async throws -> Routine
    func createRoutine(routine: Routine) async throws -> String
    func updateRoutine(id: String, routine: Routine) async throws
    func deleteRoutine(id: String, userId: String) async throws
    func setActiveRoutine(routineId: String, userId: String) async throws
    func getActiveRoutine(userId: String) async throws -> Routine?
    
    // Workout operations
    func getWorkouts(userId: String) async throws -> [Workout]
    func getWorkout(id: String, userId: String) async throws -> Workout
    func createWorkout(workout: Workout) async throws -> String
    func updateWorkout(id: String, workout: Workout) async throws
}

class CloudFunctionService: CloudFunctionServiceProtocol {
    private let functions = Functions.functions(region: "us-central1")
    
    // MARK: - Exercise Operations
    
    func getExercises() async throws -> [Exercise] {
        let data = try await callFunction(name: "getExercises", data: [:])
        return try JSONDecoder().decode([Exercise].self, from: data)
    }
    
    func getExercise(id: String) async throws -> Exercise {
        let data = try await callFunction(name: "getExercise", data: ["id": id])
        return try JSONDecoder().decode(Exercise.self, from: data)
    }
    
    // MARK: - User Operations
    
    func getUser(userId: String) async throws -> User {
        let data = try await callFunction(name: "getUser", data: ["userId": userId])
        return try JSONDecoder().decode(User.self, from: data)
    }
    
    func updateUser(userId: String, user: User) async throws {
        let data = try JSONEncoder().encode(user)
        let params = ["userId": userId, "user": String(data: data, encoding: .utf8)!]
        _ = try await callFunction(name: "updateUser", data: params)
    }
    
    // MARK: - Template Operations
    
    func getTemplates(userId: String) async throws -> [WorkoutTemplate] {
        let data = try await callFunction(name: "getUserTemplates", data: ["userId": userId])
        return try JSONDecoder().decode([WorkoutTemplate].self, from: data)
    }
    
    func getTemplate(id: String, userId: String) async throws -> WorkoutTemplate {
        let data = try await callFunction(name: "getTemplate", data: ["id": id, "userId": userId])
        return try JSONDecoder().decode(WorkoutTemplate.self, from: data)
    }
    
    func createTemplate(template: WorkoutTemplate) async throws -> String {
        let data = try JSONEncoder().encode(template)
        let params = ["template": String(data: data, encoding: .utf8)!]
        let result = try await callFunction(name: "createTemplate", data: params)
        return try JSONDecoder().decode(String.self, from: result)
    }
    
    func updateTemplate(id: String, template: WorkoutTemplate) async throws {
        let data = try JSONEncoder().encode(template)
        let params = ["id": id, "template": String(data: data, encoding: .utf8)!]
        _ = try await callFunction(name: "updateTemplate", data: params)
    }
    
    func deleteTemplate(id: String, userId: String) async throws {
        let params = ["id": id, "userId": userId]
        _ = try await callFunction(name: "deleteTemplate", data: params)
    }
    
    // MARK: - Routine Operations
    
    func getRoutines(userId: String) async throws -> [Routine] {
        let data = try await callFunction(name: "getUserRoutines", data: ["userId": userId])
        return try JSONDecoder().decode([Routine].self, from: data)
    }
    
    func getRoutine(id: String, userId: String) async throws -> Routine {
        let data = try await callFunction(name: "getRoutine", data: ["id": id, "userId": userId])
        return try JSONDecoder().decode(Routine.self, from: data)
    }
    
    func createRoutine(routine: Routine) async throws -> String {
        let data = try JSONEncoder().encode(routine)
        let params = ["routine": String(data: data, encoding: .utf8)!]
        let result = try await callFunction(name: "createRoutine", data: params)
        return try JSONDecoder().decode(String.self, from: result)
    }
    
    func updateRoutine(id: String, routine: Routine) async throws {
        let data = try JSONEncoder().encode(routine)
        let params = ["id": id, "routine": String(data: data, encoding: .utf8)!]
        _ = try await callFunction(name: "updateRoutine", data: params)
    }
    
    func deleteRoutine(id: String, userId: String) async throws {
        let params = ["id": id, "userId": userId]
        _ = try await callFunction(name: "deleteRoutine", data: params)
    }
    
    func setActiveRoutine(routineId: String, userId: String) async throws {
        let params = ["routineId": routineId, "userId": userId]
        _ = try await callFunction(name: "setActiveRoutine", data: params)
    }
    
    func getActiveRoutine(userId: String) async throws -> Routine? {
        let data = try await callFunction(name: "getActiveRoutine", data: ["userId": userId])
        return try? JSONDecoder().decode(Routine.self, from: data)
    }
    
    // MARK: - Workout Operations
    
    func getWorkouts(userId: String) async throws -> [Workout] {
        let data = try await callFunction(name: "getUserWorkouts", data: ["userId": userId])
        return try JSONDecoder().decode([Workout].self, from: data)
    }
    
    func getWorkout(id: String, userId: String) async throws -> Workout {
        let data = try await callFunction(name: "getWorkout", data: ["id": id, "userId": userId])
        return try JSONDecoder().decode(Workout.self, from: data)
    }
    
    func createWorkout(workout: Workout) async throws -> String {
        let data = try JSONEncoder().encode(workout)
        let params = ["workout": String(data: data, encoding: .utf8)!]
        let result = try await callFunction(name: "createWorkout", data: params)
        return try JSONDecoder().decode(String.self, from: result)
    }
    
    func updateWorkout(id: String, workout: Workout) async throws {
        let data = try JSONEncoder().encode(workout)
        let params = ["id": id, "workout": String(data: data, encoding: .utf8)!]
        _ = try await callFunction(name: "updateWorkout", data: params)
    }
    
    // MARK: - Private Helpers
    
    private func callFunction(name: String, data: [String: Any]) async throws -> Data {
        let result = try await functions.httpsCallable(name).call(data)
        guard let jsonData = try? JSONSerialization.data(withJSONObject: result.data) else {
            throw NSError(domain: "CloudFunctionService", code: -1, userInfo: [NSLocalizedDescriptionKey: "Failed to serialize function result"])
        }
        return jsonData
    }
}
