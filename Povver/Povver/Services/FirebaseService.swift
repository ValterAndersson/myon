import Foundation
import FirebaseFirestore

protocol FirebaseServiceProtocol {
    func getDocument<T: Codable>(collection: String, documentId: String) async throws -> T?
    func getDocuments<T: Codable>(collection: String, query: Query?) async throws -> [T]
    func addDocument<T: Codable>(collection: String, data: T) async throws -> String
    func updateDocument<T: Codable>(collection: String, documentId: String, data: T) async throws
    func deleteDocument(collection: String, documentId: String) async throws
    func createQuery(collection: String, field: String, queryOperator: QueryOperator, value: Any) -> Query
    
    // Subcollection support
    func getDocumentFromSubcollection<T: Codable>(parentCollection: String, parentDocumentId: String, subcollection: String, documentId: String) async throws -> T?
    func getDocumentsFromSubcollection<T: Codable>(parentCollection: String, parentDocumentId: String, subcollection: String, query: Query?) async throws -> [T]
    func addDocumentToSubcollection<T: Codable>(parentCollection: String, parentDocumentId: String, subcollection: String, data: T) async throws -> String
    func updateDocumentInSubcollection<T: Codable>(parentCollection: String, parentDocumentId: String, subcollection: String, documentId: String, data: T) async throws
    func deleteDocumentFromSubcollection(parentCollection: String, parentDocumentId: String, subcollection: String, documentId: String) async throws
}

enum QueryOperator {
    case equalTo
    case greaterThan
    case lessThan
    case arrayContains
    
    var firestoreOperator: String {
        switch self {
        case .equalTo: return "=="
        case .greaterThan: return ">"
        case .lessThan: return "<"
        case .arrayContains: return "array-contains"
        }
    }
}

class FirebaseService: FirebaseServiceProtocol {
    private let db: Firestore
    
    init() {
        self.db = Firestore.firestore()
    }
    
    func getDocument<T: Codable>(collection: String, documentId: String) async throws -> T? {
        let document = try await db.collection(collection).document(documentId).getDocument()
        return try document.data(as: T.self)
    }
    
    func getDocuments<T: Codable>(collection: String, query: Query? = nil) async throws -> [T] {
        let snapshot = try await (query ?? db.collection(collection)).getDocuments()
        return try snapshot.documents.compactMap { try $0.data(as: T.self) }
    }
    
    func addDocument<T: Codable>(collection: String, data: T) async throws -> String {
        let docRef = try await db.collection(collection).addDocument(from: data)
        return docRef.documentID
    }
    
    func updateDocument<T: Codable>(collection: String, documentId: String, data: T) async throws {
        try await db.collection(collection).document(documentId).setData(from: data)
    }
    
    func deleteDocument(collection: String, documentId: String) async throws {
        try await db.collection(collection).document(documentId).delete()
    }
    
    func createQuery(collection: String, field: String, queryOperator: QueryOperator, value: Any) -> Query {
        let collection = db.collection(collection)
        
        switch queryOperator {
        case .equalTo:
            return collection.whereField(field, isEqualTo: value)
        case .greaterThan:
            return collection.whereField(field, isGreaterThan: value)
        case .lessThan:
            return collection.whereField(field, isLessThan: value)
        case .arrayContains:
            return collection.whereField(field, arrayContains: value)
        }
    }
    
    // MARK: - Subcollection Methods
    
    func getDocumentFromSubcollection<T: Codable>(parentCollection: String, parentDocumentId: String, subcollection: String, documentId: String) async throws -> T? {
        let document = try await db.collection(parentCollection).document(parentDocumentId).collection(subcollection).document(documentId).getDocument()
        return try document.data(as: T.self)
    }
    
    func getDocumentsFromSubcollection<T: Codable>(parentCollection: String, parentDocumentId: String, subcollection: String, query: Query? = nil) async throws -> [T] {
        let subcollectionRef = db.collection(parentCollection).document(parentDocumentId).collection(subcollection)
        let snapshot = try await (query ?? subcollectionRef).getDocuments()
        return try snapshot.documents.compactMap { try $0.data(as: T.self) }
    }
    
    func addDocumentToSubcollection<T: Codable>(parentCollection: String, parentDocumentId: String, subcollection: String, data: T) async throws -> String {
        let docRef = try await db.collection(parentCollection).document(parentDocumentId).collection(subcollection).addDocument(from: data)
        return docRef.documentID
    }
    
    func updateDocumentInSubcollection<T: Codable>(parentCollection: String, parentDocumentId: String, subcollection: String, documentId: String, data: T) async throws {
        try await db.collection(parentCollection).document(parentDocumentId).collection(subcollection).document(documentId).setData(from: data)
    }
    
    func deleteDocumentFromSubcollection(parentCollection: String, parentDocumentId: String, subcollection: String, documentId: String) async throws {
        try await db.collection(parentCollection).document(parentDocumentId).collection(subcollection).document(documentId).delete()
    }
} 
