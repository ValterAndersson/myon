import SwiftUI

public typealias CardActionHandler = (_ action: CardAction, _ card: CanvasCardModel) -> Void

private struct CardActionHandlerKey: EnvironmentKey {
    static let defaultValue: CardActionHandler = { _, _ in }
}

public extension EnvironmentValues {
    var cardActionHandler: CardActionHandler {
        get { self[CardActionHandlerKey.self] }
        set { self[CardActionHandlerKey.self] = newValue }
    }
}


