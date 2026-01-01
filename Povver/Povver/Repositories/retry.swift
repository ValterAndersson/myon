import Foundation

public func retry<T>(times: Int, delay: TimeInterval, task: @escaping () async throws -> T) async throws -> T {
    var lastError: Error?
    for attempt in 1...times {
        do {
            return try await task()
        } catch {
            lastError = error
            if attempt < times {
                let backoff = delay * pow(2.0, Double(attempt - 1))
                try? await Task.sleep(nanoseconds: UInt64(backoff * 1_000_000_000))
            }
        }
    }
    throw lastError ?? NSError(domain: "RetryError", code: -1, userInfo: nil)
} 