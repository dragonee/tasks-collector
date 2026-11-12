import CryptoKit
import Foundation

/// The plans of the days the phone has fetched, kept so that the Today list
/// has something to show without a connection: one file per day, the agenda
/// as the server last gave it.
///
/// Each file names the account that fetched it (`account`): logged in as
/// someone else, or logged out, the phone shows none of them. Days more than
/// `keepDays` away from today are thrown away.
actor SavedPlans {

    struct Saved: Codable, Sendable {
        let account: String
        /// When it was fetched.
        let savedAt: Date
        let agenda: AgendaResponse
    }

    static let keepDays = 14

    private let dir: URL

    init(dir: URL) {
        self.dir = dir
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
    }

    /// Who fetched the plans: the server and the token, hashed. A new login
    /// has a new token, so what the last one fetched isn't shown.
    static func account(serverUrl: String, apiToken: String) -> String {
        SHA256.hash(data: Data("\(serverUrl)\n\(apiToken)".utf8))
            .map { String(format: "%02x", $0) }
            .joined()
    }

    /// Keep `agenda` as the plans of `day` (YYYY-MM-DD).
    func save(
        account: String,
        day: String,
        agenda: AgendaResponse,
        savedAt: Date = Date(),
        today: Day = .today()
    ) {
        let saved = Saved(account: account, savedAt: savedAt, agenda: agenda)
        guard let data = try? JSONEncoder().encode(saved) else { return }
        // Written aside and moved in: a read finds the old file or the new one.
        try? data.write(to: file(day), options: .atomic)
        prune(today: today)
    }

    /// The plans of `day` last fetched by `account`, or nil.
    func load(account: String, day: String) -> Saved? {
        guard let data = try? Data(contentsOf: file(day)),
              let saved = try? JSONDecoder().decode(Saved.self, from: data),
              saved.account == account
        else { return nil }
        return saved
    }

    /// Fetch the plans of `today` and of the day after and keep them, so the
    /// morning's list is on the phone before it is opened without a
    /// connection.
    func refresh(_ api: TasksClient, account: String, today: Day = .today()) async throws {
        for day in [today, today.adding(days: 1)] {
            let agenda = try await api.agenda(date: day.iso)
            save(account: account, day: day.iso, agenda: agenda, today: today)
        }
    }

    private func prune(today: Day) {
        // YYYY-MM-DD sorts as the days do.
        let first = today.adding(days: -Self.keepDays).iso
        let last = today.adding(days: Self.keepDays).iso
        let names = (try? FileManager.default.contentsOfDirectory(atPath: dir.path)) ?? []
        for name in names where name.hasSuffix(".json") {
            let day = String(name.dropLast(".json".count))
            if day < first || day > last {
                try? FileManager.default.removeItem(at: dir.appending(path: name))
            }
        }
    }

    private func file(_ day: String) -> URL {
        dir.appending(path: "\(day).json")
    }
}
