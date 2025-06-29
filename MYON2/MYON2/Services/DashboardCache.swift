import Foundation

struct CachedDashboard: Codable {
    let stats: WeeklyStats?
    let recent: [WeeklyStats]
    let goal: Int?
    let timestamp: Date
}

class DashboardCache {
    static let shared = DashboardCache()
    private let fileManager = FileManager.default
    private let directory: URL

    private init() {
        directory = fileManager.urls(for: .cachesDirectory, in: .userDomainMask).first!
    }

    private func cacheURL(for userId: String) -> URL {
        directory.appendingPathComponent("dashboard_\(userId).json")
    }

    func load(userId: String) -> CachedDashboard? {
        let url = cacheURL(for: userId)
        guard let data = try? Data(contentsOf: url) else { return nil }
        return try? JSONDecoder().decode(CachedDashboard.self, from: data)
    }

    func save(_ data: CachedDashboard, userId: String) {
        let url = cacheURL(for: userId)
        guard let encoded = try? JSONEncoder().encode(data) else { return }
        try? encoded.write(to: url, options: [.atomic])
    }

    func clear(userId: String) {
        let url = cacheURL(for: userId)
        try? fileManager.removeItem(at: url)
    }

    func isExpired(_ cache: CachedDashboard, ttl: TimeInterval = 3600) -> Bool {
        Date().timeIntervalSince(cache.timestamp) > ttl
    }
}
