import Foundation

public struct AnyCodable: Codable {
    public let value: Any
    public init(_ value: Any) { self.value = value }
    public init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        // Handle null first - treat as NSNull so we have a concrete type for Any
        if c.decodeNil() { value = NSNull(); return }
        if let i = try? c.decode(Int.self) { value = i; return }
        if let d = try? c.decode(Double.self) { value = d; return }
        if let b = try? c.decode(Bool.self) { value = b; return }
        if let s = try? c.decode(String.self) { value = s; return }
        if let arr = try? c.decode([AnyCodable].self) { value = arr.map { $0.value }; return }
        if let dict = try? c.decode([String: AnyCodable].self) { value = dict.mapValues { $0.value }; return }
        // Fallback: treat as null rather than throwing
        value = NSNull()
    }
    public func encode(to encoder: Encoder) throws {
        var c = encoder.singleValueContainer()
        switch value {
        case let i as Int: try c.encode(i)
        case let d as Double: try c.encode(d)
        case let b as Bool: try c.encode(b)
        case let s as String: try c.encode(s)
        case let arr as [Any]: try c.encode(arr.map { AnyCodable($0) })
        case let dict as [String: Any]: try c.encode(dict.mapValues { AnyCodable($0) })
        default: try c.encodeNil()
        }
    }
}
