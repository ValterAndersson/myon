import Foundation

/// ViewModel for managing routines list and active routine state
@MainActor
class RoutinesViewModel: ObservableObject {
    @Published var routines: [Routine] = []
    @Published var templates: [WorkoutTemplate] = []
    @Published var activeRoutine: Routine?
    @Published var isLoading = false
    @Published var error: String?
    
    private let routineRepository: RoutineRepositoryProtocol
    private let templateRepository: TemplateRepositoryProtocol
    private let authService: AuthService
    
    init(
        routineRepository: RoutineRepositoryProtocol = RoutineRepository(),
        templateRepository: TemplateRepositoryProtocol = TemplateRepository(),
        authService: AuthService = .shared
    ) {
        self.routineRepository = routineRepository
        self.templateRepository = templateRepository
        self.authService = authService
    }
    
    var userId: String? {
        authService.currentUserId
    }
    
    // MARK: - Load Data
    
    func loadRoutines() async {
        guard let userId = userId else {
            error = "Not logged in"
            return
        }
        
        isLoading = true
        error = nil
        
        do {
            // Load routines and templates in parallel
            async let routinesTask = routineRepository.getRoutines(userId: userId)
            async let templatesTask = templateRepository.getTemplates(userId: userId)
            async let activeTask = routineRepository.getActiveRoutine(userId: userId)
            
            let (loadedRoutines, loadedTemplates, loadedActive) = try await (routinesTask, templatesTask, activeTask)
            
            routines = loadedRoutines
            templates = loadedTemplates
            activeRoutine = loadedActive
        } catch {
            self.error = error.localizedDescription
        }
        
        isLoading = false
    }
    
    // MARK: - Template Helpers
    
    func templatesForRoutine(_ routine: Routine) -> [WorkoutTemplate] {
        routine.templateIds.compactMap { templateId in
            templates.first { $0.id == templateId }
        }
    }
    
    // MARK: - CRUD Operations
    
    func createRoutine(_ routine: Routine) async {
        guard userId != nil else { return }
        
        isLoading = true
        do {
            _ = try await routineRepository.createRoutine(routine)
            await loadRoutines()
        } catch {
            self.error = error.localizedDescription
            isLoading = false
        }
    }
    
    func updateRoutine(_ routine: Routine) async {
        isLoading = true
        do {
            try await routineRepository.updateRoutine(routine)
            await loadRoutines()
        } catch {
            self.error = error.localizedDescription
            isLoading = false
        }
    }
    
    func deleteRoutine(_ routine: Routine) async {
        guard let userId = userId else { return }
        
        isLoading = true
        do {
            try await routineRepository.deleteRoutine(id: routine.id, userId: userId)
            await loadRoutines()
        } catch {
            self.error = error.localizedDescription
            isLoading = false
        }
    }
    
    func setActiveRoutine(_ routine: Routine) async {
        guard let userId = userId else { return }
        
        isLoading = true
        do {
            try await routineRepository.setActiveRoutine(routineId: routine.id, userId: userId)
            activeRoutine = routine
            isLoading = false
        } catch {
            self.error = error.localizedDescription
            isLoading = false
        }
    }
    
    func clearActiveRoutine() async {
        guard let userId = userId else { return }
        
        isLoading = true
        do {
            try await routineRepository.setActiveRoutine(routineId: "", userId: userId)
            activeRoutine = nil
            isLoading = false
        } catch {
            self.error = error.localizedDescription
            isLoading = false
        }
    }
}
