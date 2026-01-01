import Foundation
import FirebaseCore
import FirebaseFirestore

class FirebaseConfig {
    static let shared = FirebaseConfig()
    
    private init() {}
    
    func configure() {
        FirebaseApp.configure()
    }
    
    // MARK: - Firestore References
    
    var db: Firestore {
        return Firestore.firestore()
    }
    
    // MARK: - Collection References
    
    var usersCollection: CollectionReference {
        return db.collection("users")
    }
    
    var workoutsCollection: CollectionReference {
        return db.collection("workouts")
    }
    
    var exercisesCollection: CollectionReference {
        return db.collection("exercises")
    }
} 