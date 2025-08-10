import Foundation
import FirebaseFirestore

/// Centralized timezone management - simple storage and retrieval
class TimezoneManager {
    static let shared = TimezoneManager()
    
    private let userRepository = UserRepository()
    private let queue = DispatchQueue(label: "timezone.manager", qos: .utility)
    
    // Thread-safe caching
    private var _cachedUserTimezone: String?
    private var _cachedUserId: String?
    private var _lastCacheTime: Date?
    
    // DateFormatter pooling for performance
    private var dateFormatterPool: [String: DateFormatter] = [:]
    private let formatterQueue = DispatchQueue(label: "timezone.formatter", qos: .utility)
    
    private init() {}
    
    // MARK: - Public API
    
    /// Get timezone for ANALYTICS and DATA CONSISTENCY operations
    func getAnalyticsTimezone(userId: String) async throws -> TimeZone {
        let timezoneIdentifier = try await getStoredTimezone(userId: userId)
        
        guard let timezone = TimeZone(identifier: timezoneIdentifier) else {
            return TimeZone.current
        }
        
        return timezone
    }
    
    /// Get timezone for UI DISPLAY operations
    func getUITimezone() -> TimeZone {
        return TimeZone.current
    }
    
    /// Get stored timezone identifier with thread-safe caching
    func getStoredTimezone(userId: String) async throws -> String {
        return try await withCheckedThrowingContinuation { continuation in
            queue.async { [weak self] in
                guard let self = self else {
                    continuation.resume(throwing: TimezoneError.managerDeallocated)
                    return
                }
                
                // Return cached value if valid
                if let cachedTimezone = self._cachedUserTimezone, 
                   self._cachedUserId == userId,
                   let lastCache = self._lastCacheTime,
                   Date().timeIntervalSince(lastCache) < 300 { // 5 minute cache
                    continuation.resume(returning: cachedTimezone)
                    return
                }
                
                // Fetch from Firestore
                Task {
                    do {
                        let timezone = try await self.userRepository.getUserTimezone(userId: userId)
                        
                        await MainActor.run {
                            self.queue.async {
                                self._cachedUserTimezone = timezone
                                self._cachedUserId = userId
                                self._lastCacheTime = Date()
                            }
                        }
                        
                        continuation.resume(returning: timezone)
                    } catch {
                        continuation.resume(throwing: error)
                    }
                }
            }
        }
    }
    
    /// Update user timezone
    func updateUserTimezone(userId: String, timezone: String) async throws {
        // Validate timezone identifier
        guard TimeZone(identifier: timezone) != nil else {
            throw TimezoneError.invalidTimezone(timezone)
        }
        
        // Update in Firestore
        try await userRepository.updateUserTimezone(userId: userId, timezone: timezone)
        
        // Update cache atomically
        await updateCacheAtomic(userId: userId, timezone: timezone)
        
        // Clear formatter cache (timezone changed)
        await clearFormatterCache()
    }
    
    /// Initialize timezone for new users (only if not already set)
    func initializeTimezoneIfNeeded(userId: String) async throws {
        do {
            let user = try await userRepository.getUser(userId: userId)
            
            // Only initialize if timezone is not set
            if user?.timeZone == nil {
                let currentTimezone = TimeZone.current.identifier
                try await userRepository.updateUserTimezone(userId: userId, timezone: currentTimezone)
                await updateCacheAtomic(userId: userId, timezone: currentTimezone)
            }
        } catch {
            // If user doesn't exist or any error, initialize with device timezone
            let currentTimezone = TimeZone.current.identifier
            try await userRepository.updateUserTimezone(userId: userId, timezone: currentTimezone)
            await updateCacheAtomic(userId: userId, timezone: currentTimezone)
        }
    }
    
    // MARK: - DateFormatter Management
    
    /// Get cached date formatter for analytics
    func getAnalyticsDateFormatter(userId: String, format: String) async throws -> DateFormatter {
        let timezone = try await getAnalyticsTimezone(userId: userId)
        let key = "\(format)_\(timezone.identifier)"
        
        return await withCheckedContinuation { continuation in
            formatterQueue.async { [weak self] in
                if let existing = self?.dateFormatterPool[key] {
                    continuation.resume(returning: existing)
                    return
                }
                
                let formatter = DateFormatter()
                formatter.dateFormat = format
                formatter.timeZone = timezone
                
                self?.dateFormatterPool[key] = formatter
                continuation.resume(returning: formatter)
            }
        }
    }
    
    /// Get cached date formatter for UI
    func getUIDateFormatter(format: String) -> DateFormatter {
        let key = "\(format)_UI"
        
        return formatterQueue.sync {
            if let existing = dateFormatterPool[key] {
                return existing
            }
            
            let formatter = DateFormatter()
            formatter.dateFormat = format
            formatter.timeZone = getUITimezone()
            
            dateFormatterPool[key] = formatter
            return formatter
        }
    }
    
    /// Format timezone for display
    func formatTimezoneForDisplay(_ timezoneIdentifier: String) -> String {
        guard let timeZone = TimeZone(identifier: timezoneIdentifier) else { 
            return timezoneIdentifier 
        }
        
        let offset = timeZone.secondsFromGMT() / 3600
        let offsetString = offset >= 0 ? "+\(offset)" : "\(offset)"
        
        let parts = timezoneIdentifier.split(separator: "/")
        let cityName = parts.last?.replacingOccurrences(of: "_", with: " ") ?? timezoneIdentifier
        
        return "\(cityName) (GMT\(offsetString))"
    }
    
    // MARK: - Private Helpers
    
    private func updateCacheAtomic(userId: String, timezone: String) async {
        await withCheckedContinuation { continuation in
            queue.async { [weak self] in
                self?._cachedUserTimezone = timezone
                self?._cachedUserId = userId
                self?._lastCacheTime = Date()
                continuation.resume()
            }
        }
    }
    
    private func clearFormatterCache() async {
        await withCheckedContinuation { continuation in
            formatterQueue.async { [weak self] in
                self?.dateFormatterPool.removeAll()
                continuation.resume()
            }
        }
    }
}

// MARK: - Error Types

enum TimezoneError: LocalizedError {
    case invalidTimezone(String)
    case managerDeallocated
    
    var errorDescription: String? {
        switch self {
        case .invalidTimezone(let tz):
            return "Invalid timezone identifier: \(tz)"
        case .managerDeallocated:
            return "TimezoneManager was deallocated"
        }
    }
} 