import Foundation
import FirebaseFirestore
import FirebaseAuth

protocol CanvasRepositoryProtocol {
    func subscribe(userId: String, canvasId: String) -> AsyncThrowingStream<CanvasSnapshot, Error>
}

final class CanvasRepository: CanvasRepositoryProtocol {
    static let shared = CanvasRepository()
    @MainActor var currentCanvasId: String?
    private let db = Firestore.firestore()

    func subscribe(userId: String, canvasId: String) -> AsyncThrowingStream<CanvasSnapshot, Error> {
        let stateRef = db.collection("users").document(userId).collection("canvases").document(canvasId)
        let cardsRef = stateRef.collection("cards")
        let upNextRef = stateRef.collection("up_next")

        return AsyncThrowingStream { continuation in
            var state: CanvasStateDTO = CanvasStateDTO(phase: nil, version: 0, purpose: nil, lanes: nil)
            var cards: [String: CanvasCardModel] = [:]
            var upNext: [String] = []

            func emit() {
                let version = state.version ?? 0
                let snapshot = CanvasSnapshot(version: version, state: state, cards: Array(cards.values), upNext: upNext)
                continuation.yield(snapshot)
            }

            let stateListener = stateRef.addSnapshotListener { snap, err in
                if let err { continuation.finish(throwing: err); return }
                guard let data = snap?.data() else { return }
                if let st = data["state"] as? [String: Any] {
                    let phase = (st["phase"] as? String).flatMap { CanvasPhase(rawValue: $0) }
                    let version = st["version"] as? Int
                    let purpose = st["purpose"] as? String
                    let lanes = st["lanes"] as? [String]
                    state = CanvasStateDTO(phase: phase, version: version, purpose: purpose, lanes: lanes)
                    emit()
                }
            }

            let cardsListener = cardsRef.addSnapshotListener { snap, err in
                if let err { continuation.finish(throwing: err); return }
                guard let docs = snap?.documents else { return }
                cards.removeAll()
                for doc in docs {
                    if let model = CanvasMapper.mapCard(from: doc) {
                        cards[model.id] = model
                    }
                }
                emit()
            }

            let upNextListener = upNextRef.order(by: "priority", descending: true).addSnapshotListener { snap, err in
                if let err { continuation.finish(throwing: err); return }
                guard let docs = snap?.documents else { return }
                upNext = docs.compactMap { $0.data()["card_id"] as? String }
                emit()
            }

            continuation.onTermination = { _ in
                stateListener.remove()
                cardsListener.remove()
                upNextListener.remove()
            }
        }
    }
}


