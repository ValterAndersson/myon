import Foundation

@MainActor
class TemplateManager: ObservableObject {
    static let shared = TemplateManager()
    
    @Published private(set) var currentTemplate: WorkoutTemplate?
    @Published private(set) var isEditing: Bool = false
    @Published private(set) var currentAnalytics: TemplateAnalytics?
    
    // Performance optimization - batch UI updates
    private var pendingUpdates: [() -> Void] = []
    private var updateTimer: Timer?
    
    // Dependencies
    private let exercisesViewModel = ExercisesViewModel()
    
    private init() {}
    
    // MARK: - Template Lifecycle
    func startEditing(template: WorkoutTemplate? = nil) {
        let editingTemplate = template ?? createNewTemplate()
        self.currentTemplate = editingTemplate
        self.isEditing = true
        
        // Load exercises if needed and calculate analytics
        loadExercisesAndCalculateAnalytics()
    }
    
    func stopEditing() {
        DispatchQueue.main.async { [weak self] in
            self?.currentTemplate = nil
            self?.isEditing = false
            self?.currentAnalytics = nil
        }
    }
    
    func saveTemplate() async throws -> String? {
        guard var template = currentTemplate else { return nil }
        
        // Ensure updated timestamp
        template.updatedAt = Date()
        
        // Include computed analytics in the saved template (safely)
        if let analytics = currentAnalytics {
            // Verify analytics data is valid before saving
            if analytics.totalSets > 0 && !analytics.projectedVolumePerMuscleGroup.isEmpty {
                template.analytics = analytics
            }
        }
        
        // Use CloudFunctionService for template operations
        let service = CloudFunctionService()
        
        // Check if this is an edit (existing template with userId set) or create new
        let isEditing = !template.userId.isEmpty && template.createdAt < template.updatedAt
        
        do {
            if isEditing {
                // Update existing template
                try await service.updateTemplate(id: template.id, template: template)
                return template.id
            } else {
                // Create new template
                let templateId = try await service.createTemplate(template: template)
                return templateId
            }
        } catch {
            // If save fails with analytics, try saving without analytics
            template.analytics = nil
            
            if isEditing {
                try await service.updateTemplate(id: template.id, template: template)
                return template.id
            } else {
                let templateId = try await service.createTemplate(template: template)
                return templateId
            }
        }
    }
    
    // MARK: - Template Properties
    func updateName(_ name: String) {
        guard var template = currentTemplate else { return }
        template.name = name
        batchUpdate { [weak self] in
            self?.currentTemplate = template
        }
    }
    
    func updateDescription(_ description: String?) {
        guard var template = currentTemplate else { return }
        template.description = description?.isEmpty == true ? nil : description
        batchUpdate { [weak self] in
            self?.currentTemplate = template
        }
    }
    
    // MARK: - Exercise Management
    func addExercise(_ exercise: Exercise, at position: Int? = nil) {
        guard var template = currentTemplate else { return }
        
        let templateExercise = WorkoutTemplateExercise(
            id: UUID().uuidString,
            exerciseId: exercise.id,
            position: position ?? template.exercises.count,
            sets: [],
            restBetweenSets: nil
        )
        
        if let position = position {
            template.exercises.insert(templateExercise, at: position)
            updateExercisePositions(&template.exercises)
        } else {
            template.exercises.append(templateExercise)
        }
        
        batchUpdate { [weak self] in
            self?.currentTemplate = template
            self?.calculateAnalytics()
        }
    }
    
    func removeExercise(id: String) {
        guard var template = currentTemplate else { return }
        template.exercises.removeAll { $0.id == id }
        updateExercisePositions(&template.exercises)
        
        batchUpdate { [weak self] in
            self?.currentTemplate = template
            self?.calculateAnalytics()
        }
    }
    
    func moveExercise(from: Int, to: Int) {
        guard var template = currentTemplate else { return }
        guard from < template.exercises.count && to < template.exercises.count else { return }
        
        let exercise = template.exercises.remove(at: from)
        template.exercises.insert(exercise, at: to)
        updateExercisePositions(&template.exercises)
        
        batchUpdate { [weak self] in
            self?.currentTemplate = template
            self?.calculateAnalytics()
        }
    }
    
    // MARK: - Set Management
    func addSet(toExerciseId: String, reps: Int = 0, weight: Double = 0, rir: Int = 2, type: String = "Working Set") {
        guard var template = currentTemplate else { return }
        guard let idx = template.exercises.firstIndex(where: { $0.id == toExerciseId }) else { return }
        
        let newSet = WorkoutTemplateSet(
            id: UUID().uuidString,
            reps: reps,
            rir: rir,
            type: type,
            weight: weight,
            duration: nil
        )
        
        template.exercises[idx].sets.append(newSet)
        
        batchUpdate { [weak self] in
            self?.currentTemplate = template
            self?.calculateAnalytics()
        }
    }
    
    func updateSet(exerciseId: String, set: WorkoutTemplateSet) {
        guard var template = currentTemplate else { return }
        guard let exIdx = template.exercises.firstIndex(where: { $0.id == exerciseId }) else { return }
        if let setIdx = template.exercises[exIdx].sets.firstIndex(where: { $0.id == set.id }) {
            template.exercises[exIdx].sets[setIdx] = set
            
            batchUpdate { [weak self] in
                self?.currentTemplate = template
                self?.calculateAnalytics()
            }
        }
    }
    
    func removeSet(exerciseId: String, setId: String) {
        guard var template = currentTemplate else { return }
        guard let exIdx = template.exercises.firstIndex(where: { $0.id == exerciseId }) else { return }
        template.exercises[exIdx].sets.removeAll { $0.id == setId }
        
        batchUpdate { [weak self] in
            self?.currentTemplate = template
            self?.calculateAnalytics()
        }
    }
    
    // MARK: - Set Property Updates
    func updateSetWeight(exerciseId: String, setId: String, weight: Double) {
        guard var template = currentTemplate else { return }
        guard let exIdx = template.exercises.firstIndex(where: { $0.id == exerciseId }) else { return }
        if let setIdx = template.exercises[exIdx].sets.firstIndex(where: { $0.id == setId }) {
            template.exercises[exIdx].sets[setIdx].weight = weight
            
            batchUpdate { [weak self] in
                self?.currentTemplate = template
                self?.calculateAnalytics()
            }
        }
    }
    
    func updateSetReps(exerciseId: String, setId: String, reps: Int) {
        guard var template = currentTemplate else { return }
        guard let exIdx = template.exercises.firstIndex(where: { $0.id == exerciseId }) else { return }
        if let setIdx = template.exercises[exIdx].sets.firstIndex(where: { $0.id == setId }) {
            template.exercises[exIdx].sets[setIdx].reps = reps
            
            batchUpdate { [weak self] in
                self?.currentTemplate = template
                self?.calculateAnalytics()
            }
        }
    }
    
    func updateSetRir(exerciseId: String, setId: String, rir: Int) {
        guard var template = currentTemplate else { return }
        guard let exIdx = template.exercises.firstIndex(where: { $0.id == exerciseId }) else { return }
        if let setIdx = template.exercises[exIdx].sets.firstIndex(where: { $0.id == setId }) {
            template.exercises[exIdx].sets[setIdx].rir = rir
            
            batchUpdate { [weak self] in
                self?.currentTemplate = template
                self?.calculateAnalytics()
            }
        }
    }
    
    func updateSetType(exerciseId: String, setId: String, type: String) {
        guard var template = currentTemplate else { return }
        guard let exIdx = template.exercises.firstIndex(where: { $0.id == exerciseId }) else { return }
        if let setIdx = template.exercises[exIdx].sets.firstIndex(where: { $0.id == setId }) {
            template.exercises[exIdx].sets[setIdx].type = type
            
            batchUpdate { [weak self] in
                self?.currentTemplate = template
                self?.calculateAnalytics()
            }
        }
    }
    
    // MARK: - Analytics
    private func loadExercisesAndCalculateAnalytics() {
        Task {
            if exercisesViewModel.exercises.isEmpty {
                await exercisesViewModel.loadExercises()
            }
            let exercises = exercisesViewModel.exercises
            self.calculateAnalytics(with: exercises)
        }
    }
    
    private func calculateAnalytics(with exercises: [Exercise]? = nil) {
        guard let template = currentTemplate, !template.exercises.isEmpty else {
            currentAnalytics = nil
            return
        }
        
        // Use provided exercises or get them from the view model
        let exercisesToUse: [Exercise]
        if let exercises = exercises {
            exercisesToUse = exercises
        } else {
            // This will only work if called from MainActor context
            exercisesToUse = exercisesViewModel.exercises
        }
        
        guard !exercisesToUse.isEmpty else {
            currentAnalytics = nil
            return
        }
        
        // Calculate simple analytics without external dependency
        var totalSets = 0
        var totalReps = 0
        var projectedVolume: Double = 0
        var volumeByMuscle: [String: Double] = [:]
        
        for templateExercise in template.exercises {
            // Find matching exercise to get muscle group info
            let matchingExercise = exercisesToUse.first { $0.id == templateExercise.exerciseId }
            let primaryMuscle = matchingExercise?.primaryMuscles.first ?? "Unknown"
            
            for set in templateExercise.sets {
                totalSets += 1
                totalReps += set.reps
                let setVolume = set.weight * Double(set.reps)
                projectedVolume += setVolume
                volumeByMuscle[primaryMuscle, default: 0] += setVolume
            }
        }
        
        // Estimate duration: ~2 min per set average (including rest)
        let estimatedDuration = totalSets * 2
        
        currentAnalytics = TemplateAnalytics(
            totalSets: totalSets,
            totalReps: totalReps,
            projectedVolume: projectedVolume,
            projectedVolumePerMuscleGroup: volumeByMuscle,
            estimatedDuration: estimatedDuration
        )
    }
    
    // MARK: - Private Helpers
    private func createNewTemplate() -> WorkoutTemplate {
        WorkoutTemplate(
            id: UUID().uuidString,
            userId: getCurrentUserId() ?? "",
            name: "",
            description: nil,
            exercises: [],
            analytics: nil,
            createdAt: Date(),
            updatedAt: Date()
        )
    }
    
    private func getCurrentUserId() -> String? {
        return AuthService.shared.currentUser?.uid
    }
    
    private func updateExercisePositions(_ exercises: inout [WorkoutTemplateExercise]) {
        for (index, var exercise) in exercises.enumerated() {
            exercise.position = index
            exercises[index] = exercise
        }
    }
    
    // MARK: - Performance Optimization
    private func batchUpdate(_ update: @escaping () -> Void) {
        pendingUpdates.append(update)
        
        // Debounce updates to prevent UI lag during rapid typing
        updateTimer?.invalidate()
        updateTimer = Timer.scheduledTimer(withTimeInterval: 0.1, repeats: false) { [weak self] _ in
            Task { @MainActor in
                self?.flushPendingUpdates()
            }
        }
    }
    
    private func flushPendingUpdates() {
        DispatchQueue.main.async { [weak self] in
            guard let self = self else { return }
            for update in self.pendingUpdates {
                update()
            }
            self.pendingUpdates.removeAll()
        }
    }
}
