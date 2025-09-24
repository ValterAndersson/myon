import SwiftUI

public enum ValidationState: Equatable {
    case normal
    case success(message: String? = nil)
    case error(message: String? = nil)

    public var color: Color {
        switch self {
        case .normal: return ColorsToken.Border.default
        case .success: return ColorsToken.State.success
        case .error: return ColorsToken.State.error
        }
    }

    public var message: String? {
        switch self {
        case .normal: return nil
        case .success(let m): return m
        case .error(let m): return m
        }
    }
}


