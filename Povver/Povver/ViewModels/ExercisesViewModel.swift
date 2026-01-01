import Foundation
import Combine

@MainActor
class ExercisesViewModel: ObservableObject {
    @Published var exercises: [Exercise] = []
    @Published var isLoading = false
    @Published var error: Error?
    
    // Filter options
    @Published var categories: [String] = []
    @Published var movementTypes: [String] = []
    @Published var levels: [String] = []
    @Published var equipment: [String] = []
    @Published var primaryMuscles: [String] = []
    @Published var secondaryMuscles: [String] = []
    
    // Current filter and search state
    private var allExercises: [Exercise] = []
    private var currentSearchQuery: String = ""
    private var currentFilters: [String: String?] = [
        "category": nil,
        "movementType": nil,
        "level": nil,
        "equipment": nil,
        "primaryMuscle": nil,
        "secondaryMuscle": nil
    ]
    
    private let repository: ExerciseRepository
    
    init(repository: ExerciseRepository = ExerciseRepository()) {
        self.repository = repository
    }
    
    func loadExercises() async {
        isLoading = true
        error = nil
        
        do {
            allExercises = try await repository.list()
            await loadFilterOptions()
            await applyFiltersAndSearch()
        } catch {
            self.error = error
        }
        
        isLoading = false
    }
    
    private func loadFilterOptions() async {
        // Extract unique values from all exercises
        categories = Array(Set(allExercises.map { $0.category })).sorted()
        movementTypes = Array(Set(allExercises.map { $0.movementType })).sorted()
        levels = Array(Set(allExercises.map { $0.level })).sorted()
        equipment = Array(Set(allExercises.flatMap { $0.equipment })).sorted()
        primaryMuscles = Array(Set(allExercises.flatMap { $0.primaryMuscles })).sorted()
        secondaryMuscles = Array(Set(allExercises.flatMap { $0.secondaryMuscles })).sorted()
    }
    
    func searchExercises(query: String) async {
        currentSearchQuery = query
        await applyFiltersAndSearch()
    }
    
    func filterByCategory(_ category: String?) async {
        currentFilters["category"] = category
        await applyFiltersAndSearch()
    }
    
    func filterByMovementType(_ type: String?) async {
        currentFilters["movementType"] = type
        await applyFiltersAndSearch()
    }
    
    func filterByLevel(_ level: String?) async {
        currentFilters["level"] = level
        await applyFiltersAndSearch()
    }
    
    func filterByEquipment(_ equipment: String?) async {
        currentFilters["equipment"] = equipment
        await applyFiltersAndSearch()
    }
    
    func filterByPrimaryMuscle(_ muscle: String?) async {
        currentFilters["primaryMuscle"] = muscle
        await applyFiltersAndSearch()
    }
    
    func filterBySecondaryMuscle(_ muscle: String?) async {
        currentFilters["secondaryMuscle"] = muscle
        await applyFiltersAndSearch()
    }
    
    private func applyFiltersAndSearch() async {
        var filteredExercises = allExercises
        
        // Apply category filter
        if let category = currentFilters["category"], let categoryValue = category {
            filteredExercises = filteredExercises.filter { $0.category == categoryValue }
        }
        
        // Apply movement type filter
        if let movementType = currentFilters["movementType"], let movementTypeValue = movementType {
            filteredExercises = filteredExercises.filter { $0.movementType == movementTypeValue }
        }
        
        // Apply level filter
        if let level = currentFilters["level"], let levelValue = level {
            filteredExercises = filteredExercises.filter { $0.level == levelValue }
        }
        
        // Apply equipment filter
        if let equipment = currentFilters["equipment"], let equipmentValue = equipment {
            filteredExercises = filteredExercises.filter { $0.equipment.contains(equipmentValue) }
        }
        
        // Apply primary muscle filter
        if let primaryMuscle = currentFilters["primaryMuscle"], let primaryMuscleValue = primaryMuscle {
            filteredExercises = filteredExercises.filter { $0.primaryMuscles.contains(primaryMuscleValue) }
        }
        
        // Apply secondary muscle filter
        if let secondaryMuscle = currentFilters["secondaryMuscle"], let secondaryMuscleValue = secondaryMuscle {
            filteredExercises = filteredExercises.filter { $0.secondaryMuscles.contains(secondaryMuscleValue) }
        }
        
        // Apply search query
        if !currentSearchQuery.isEmpty {
            let searchTerm = currentSearchQuery.lowercased()
            filteredExercises = filteredExercises.filter { exercise in
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
        
        exercises = filteredExercises
    }
} 