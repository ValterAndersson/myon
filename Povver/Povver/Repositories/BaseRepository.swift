import Foundation
import FirebaseFirestore

protocol BaseRepository {
    associatedtype T: Codable
    
    var collection: CollectionReference { get }
    
    func create(_ item: T) async throws
    func read(id: String) async throws -> T?
    func update(_ item: T, id: String) async throws
    func delete(id: String) async throws
    func list() async throws -> [T]
}

class FirestoreRepository<T: Codable>: BaseRepository {
    let collection: CollectionReference
    
    init(collection: CollectionReference) {
        self.collection = collection
    }
    
    func create(_ item: T) async throws {
        try collection.addDocument(from: item)
    }
    
    func read(id: String) async throws -> T? {
        let document = try await collection.document(id).getDocument()
        return try document.data(as: T.self)
    }
    
    func update(_ item: T, id: String) async throws {
        try collection.document(id).setData(from: item)
    }
    
    func delete(id: String) async throws {
        try await collection.document(id).delete()
    }
    
    func list() async throws -> [T] {
        let snapshot = try await collection.getDocuments()
        return try snapshot.documents.compactMap { try $0.data(as: T.self) }
    }
}
