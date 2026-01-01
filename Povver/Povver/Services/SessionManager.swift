import Foundation
import Combine

class SessionManager: ObservableObject {
    static let shared = SessionManager()
    
    @Published private(set) var userId: String?
    @Published private(set) var activeWorkoutId: String?
    
    private let userIdKey = "userId"
    private let activeWorkoutIdKey = "activeWorkoutId"
    private let queue = DispatchQueue(label: "SessionManagerQueue", qos: .userInitiated)
    
    private init() {
        // Restore session from UserDefaults asynchronously
        queue.async { [weak self] in
            let userId = UserDefaults.standard.string(forKey: self?.userIdKey ?? "")
            let activeWorkoutId = UserDefaults.standard.string(forKey: self?.activeWorkoutIdKey ?? "")
            DispatchQueue.main.async {
                self?.userId = userId
                self?.activeWorkoutId = activeWorkoutId
            }
        }
    }
    
    func startSession(userId: String) {
        queue.async { [weak self] in
            UserDefaults.standard.set(userId, forKey: self?.userIdKey ?? "")
            DispatchQueue.main.async {
                self?.userId = userId
            }
        }
    }
    
    func endSession() {
        queue.async { [weak self] in
            UserDefaults.standard.removeObject(forKey: self?.userIdKey ?? "")
            UserDefaults.standard.removeObject(forKey: self?.activeWorkoutIdKey ?? "")
            DispatchQueue.main.async {
                self?.userId = nil
                self?.activeWorkoutId = nil
            }
        }
    }
    
    func setActiveWorkout(id: String?) {
        queue.async { [weak self] in
            if let id = id {
                UserDefaults.standard.set(id, forKey: self?.activeWorkoutIdKey ?? "")
            } else {
                UserDefaults.standard.removeObject(forKey: self?.activeWorkoutIdKey ?? "")
            }
            DispatchQueue.main.async {
                self?.activeWorkoutId = id
            }
        }
    }
} 