import Foundation
import Observation
import Security

struct SettingsSnapshot: Equatable, Sendable {
    var serverUrl = ""
    var apiToken = ""
    var lastSyncEpochMs: Int64 = 0
    var lastSyncError = ""

    var isConfigured: Bool {
        !serverUrl.trimmingCharacters(in: .whitespaces).isEmpty
            && !apiToken.trimmingCharacters(in: .whitespaces).isEmpty
    }
}

/// What the app remembers between launches: the server and the token for it,
/// how the last health sync went, and what location tracking is doing.
///
/// The token is in the keychain, the rest in UserDefaults. A debug build
/// falls back to the defaults of ios/Local.xcconfig while nothing is saved,
/// so a fresh install comes up pointed at the dev server.
@MainActor
@Observable
final class Settings {

    private(set) var snapshot: SettingsSnapshot

    /// Whether location tracking is paused. One trail is recorded for all
    /// trips, and pausing stops sampling without dropping it; only the last
    /// trip finishing clears it (and this flag).
    private(set) var trackingPaused: Bool

    @ObservationIgnored private let defaults: UserDefaults
    @ObservationIgnored private let keychain: Keychain

    init(defaults: UserDefaults = .standard, keychain: Keychain = Keychain(service: Bundle.main.bundleIdentifier ?? "tasks-health")) {
        self.defaults = defaults
        self.keychain = keychain
        trackingPaused = defaults.bool(forKey: Key.trackingPaused)
        snapshot = SettingsSnapshot()
        snapshot = read()
    }

    private func read() -> SettingsSnapshot {
        let url = defaults.string(forKey: Key.serverUrl) ?? ""
        let token = keychain.get(Key.apiToken) ?? ""
        return SettingsSnapshot(
            serverUrl: url.isEmpty ? Self.devDefault("TasksDevServerURL") : url,
            apiToken: token.isEmpty ? Self.devDefault("TasksDevAPIToken") : token,
            lastSyncEpochMs: Int64(defaults.integer(forKey: Key.lastSyncMs)),
            lastSyncError: defaults.string(forKey: Key.lastSyncError) ?? ""
        )
    }

    private static func devDefault(_ key: String) -> String {
        (Bundle.main.object(forInfoDictionaryKey: key) as? String) ?? ""
    }

    func saveServerConfig(url: String, token: String) {
        defaults.set(url.trimmingCharacters(in: .whitespacesAndNewlines), forKey: Key.serverUrl)
        keychain.set(token.trimmingCharacters(in: .whitespacesAndNewlines), for: Key.apiToken)
        snapshot = read()
    }

    func recordSyncSuccess(at date: Date = Date()) {
        defaults.set(Int(date.epochMillis), forKey: Key.lastSyncMs)
        defaults.removeObject(forKey: Key.lastSyncError)
        snapshot = read()
    }

    func recordSyncFailure(_ error: String) {
        defaults.set(error, forKey: Key.lastSyncError)
        snapshot = read()
    }

    /// Ids of bike rides already posted to the server, so that the 7-day
    /// re-sync doesn't post a ride again. Rides don't change once finished.
    var syncedBikeSessionIds: Set<String> {
        Set(defaults.stringArray(forKey: Key.syncedBikeSessionIds) ?? [])
    }

    func addSyncedBikeSessionId(_ id: String) {
        defaults.set(Array(syncedBikeSessionIds.union([id])), forKey: Key.syncedBikeSessionIds)
    }

    /// Ids of the trips whose location is being tracked on this phone: what
    /// says whether the recorder should run. Survives the app being killed
    /// (tracking resumes when it is opened again).
    var trackedStoryIds: Set<Int64> {
        Set((defaults.stringArray(forKey: Key.trackedStoryIds) ?? []).compactMap { Int64($0) })
    }

    func setTrackedStoryIds(_ ids: Set<Int64>) {
        defaults.set(ids.map(String.init), forKey: Key.trackedStoryIds)
    }

    func setTrackingPaused(_ paused: Bool) {
        defaults.set(paused, forKey: Key.trackingPaused)
        trackingPaused = paused
    }

    private enum Key {
        static let serverUrl = "server_url"
        static let apiToken = "api_token"
        static let lastSyncMs = "last_sync_ms"
        static let lastSyncError = "last_sync_error"
        static let syncedBikeSessionIds = "synced_bike_session_ids"
        static let trackedStoryIds = "tracked_story_ids"
        static let trackingPaused = "tracking_paused"
    }
}

/// Generic passwords of this app in the keychain.
struct Keychain: Sendable {
    let service: String

    func get(_ account: String) -> String? {
        var query = base(account)
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        var found: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &found) == errSecSuccess,
              let data = found as? Data
        else { return nil }
        return String(data: data, encoding: .utf8)
    }

    /// Keep `value` under `account`; an empty one forgets it.
    func set(_ value: String, for account: String) {
        SecItemDelete(base(account) as CFDictionary)
        guard !value.isEmpty else { return }
        var item = base(account)
        item[kSecValueData as String] = Data(value.utf8)
        // Readable while the phone is locked, once it has been unlocked
        // since boot: a background sync needs the token.
        item[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlock
        SecItemAdd(item as CFDictionary, nil)
    }

    private func base(_ account: String) -> [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
    }
}
