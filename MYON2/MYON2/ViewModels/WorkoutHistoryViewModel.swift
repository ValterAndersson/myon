import Foundation
import Combine

@MainActor
class WorkoutHistoryViewModel: ObservableObject {
    @Published var workouts: [Workout] = []
    @Published var filteredWorkouts: [Workout] = []
    @Published var templates: [WorkoutTemplate] = []
    @Published var isLoading = false
    @Published var error: Error?
    
    private let workoutRepository = WorkoutRepository()
    private let templateRepository = TemplateRepository()
    
    func loadWorkouts() async {
        isLoading = true
        error = nil
        
        do {
            guard let userId = AuthService.shared.currentUser?.uid else {
                self.error = WorkoutError.noUserID
                isLoading = false
                return
            }
            
            // Load workouts and templates in parallel
            async let workoutsTask = workoutRepository.getWorkouts(userId: userId)
            async let templatesTask = templateRepository.getTemplates(userId: userId)
            
            let (fetchedWorkouts, fetchedTemplates) = try await (workoutsTask, templatesTask)
            
            workouts = fetchedWorkouts.sorted { $0.endTime > $1.endTime }
            templates = fetchedTemplates
            filteredWorkouts = workouts
        } catch {
            self.error = error
        }
        
        isLoading = false
    }
    
    func filterWorkouts(searchText: String, timeFrame: WorkoutHistoryView.TimeFrame) {
        var filtered = workouts
        
        // Apply time frame filter
        switch timeFrame {
        case .week:
            let weekAgo = Calendar.current.date(byAdding: .weekOfYear, value: -1, to: Date()) ?? Date()
            filtered = filtered.filter { $0.endTime >= weekAgo }
        case .month:
            let monthAgo = Calendar.current.date(byAdding: .month, value: -1, to: Date()) ?? Date()
            filtered = filtered.filter { $0.endTime >= monthAgo }
        case .year:
            let yearAgo = Calendar.current.date(byAdding: .year, value: -1, to: Date()) ?? Date()
            filtered = filtered.filter { $0.endTime >= yearAgo }
        case .allTime:
            // No filter
            break
        }
        
        // Apply search filter
        if !searchText.isEmpty {
            let searchTerm = searchText.lowercased()
            filtered = filtered.filter { workout in
                // Search in template name if available
                let templateName = getTemplateName(for: workout.sourceTemplateId)?.lowercased() ?? ""
                
                // Search in exercise names
                let exerciseNames = workout.exercises.map { $0.name.lowercased() }.joined(separator: " ")
                
                return templateName.contains(searchTerm) || exerciseNames.contains(searchTerm)
            }
        }
        
        filteredWorkouts = filtered
    }
    
    func getTemplateName(for templateId: String?) -> String? {
        guard let templateId = templateId else { return nil }
        return templates.first { $0.id == templateId }?.name
    }
    
    func getWorkingSetsCount(for exercise: WorkoutExercise) -> Int {
        return exercise.sets.filter { isWorkingSet($0.type) }.count
    }
    
    func formatDuration(_ start: Date, _ end: Date) -> String {
        let duration = end.timeIntervalSince(start)
        let hours = Int(duration) / 3600
        let minutes = (Int(duration) % 3600) / 60
        
        if hours > 0 {
            return "\(hours)h \(minutes)m"
        } else {
            return "\(minutes)m"
        }
    }
    
    func formatDate(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.dateStyle = .medium
        return formatter.string(from: date)
    }
    
    func formatTime(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.timeStyle = .short
        return formatter.string(from: date)
    }
}

// Helper function to determine if a set type is a working set
private func isWorkingSet(_ type: String) -> Bool {
    let workingSetTypes = ["Working Set", "Drop Set", "Rest-Pause Set", "Cluster Set", "Tempo Set"]
    return workingSetTypes.contains(type)
} 