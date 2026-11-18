import AuthenticationServices
import Observation
import UIKit

/// The "register activity" sheet while it is open, with the keyword it
/// opens on (weight when opened from the weight row; nil for the first).
struct ActivitySheet: Identifiable, Equatable {
    let id = UUID()
    let keyword: String?
}

/// Behind the Health and Settings screens: logging in and out, the health
/// metrics on show, and registering an activity.
@MainActor
@Observable
final class MainModel {

    @ObservationIgnored private unowned let services: AppServices
    @ObservationIgnored private let webLogin = WebLogin()

    /// Whether the user has been asked for access to HealthKit.
    private(set) var healthAccessRequested = false
    private(set) var todayMetrics: DailyMetrics?
    /// Server-derived health data (the weight last recorded); nil until loaded.
    private(set) var healthData: HealthDataResponse?

    /// The "register activity" sheet: nil while closed.
    var activitySheet: ActivitySheet?
    /// The habits the sheet offers, by keyword, each with what it records;
    /// fetched again each time it opens.
    private(set) var activityKeywords: [HabitKeyword] = []
    /// True while an activity is being posted.
    private(set) var activitySaving = false
    private(set) var activityError: String?

    /// True while a login or a logout is being settled with the server.
    private(set) var loginBusy = false
    /// Why the last login or logout didn't work (nil: it did, or none yet).
    private(set) var loginError: String?

    let healthAvailable = HealthRepository.isAvailable

    /// Where the server sends the browser back to: this build of the app.
    private let bundleId = Bundle.main.bundleIdentifier ?? "org.polybrain.tasks.health"

    init(_ services: AppServices) {
        self.services = services
    }

    private var settings: Settings { services.settings }

    // MARK: Health

    func refresh() async {
        healthAccessRequested = await services.health.accessRequested()
        await refreshMetrics()
        await refreshHealthData()
    }

    func requestHealthAccess() async {
        try? await services.health.requestAccess()
        healthAccessRequested = await services.health.accessRequested()
        await refreshMetrics()
    }

    private func refreshMetrics() async {
        guard healthAccessRequested else { return }
        todayMetrics = try? await services.health.aggregateDay(.today())
    }

    private func refreshHealthData() async {
        let snapshot = settings.snapshot
        guard snapshot.isConfigured else { return }
        if let data = try? await TasksClient(snapshot).healthData() {
            healthData = data
        }
    }

    func syncNow() async {
        await services.syncHealthNow()
        await refreshMetrics()
        await refreshHealthData()
    }

    // MARK: Logging in

    func save(serverUrl: String, apiToken: String) {
        settings.saveServerConfig(url: serverUrl, token: apiToken)
        services.outboxSync.kick()
        Task { await refreshHealthData() }
    }

    /// Log in to `serverUrl` (see `OAuthLogin`): the server's page opens in
    /// a browser sheet, where the user logs in as on the web; what the
    /// browser comes back with is traded for a token, kept with the server
    /// it is for.
    func login(serverUrl: String) async {
        let pending = OAuthLogin.start(serverUrl: serverUrl)
        let redirectUri = OAuthLogin.redirectUri(bundleId: bundleId)
        guard let url = OAuthLogin.authorizeUrl(pending, redirectUri: redirectUri, deviceName: UIDevice.current.name) else {
            loginError = "That is not a server URL."
            return
        }
        loginError = nil

        let callback: URL
        do {
            callback = try await webLogin.open(url, callbackScheme: bundleId)
        } catch let error as ASWebAuthenticationSessionError where error.code == .canceledLogin {
            loginError = "The login was cancelled."
            return
        } catch {
            loginError = error.localizedDescription
            return
        }

        let code: String
        switch OAuthLogin.codeFrom(pending, callback: callback) {
        case .code(let got): code = got
        case .refused(let reason):
            loginError = reason
            return
        }

        loginBusy = true
        defer { loginBusy = false }
        do {
            let token = try await TasksClient.exchangeCode(pending, code: code, redirectUri: redirectUri)
            settings.saveServerConfig(url: pending.serverUrl, token: token)
            // What was queued while logged out can go now.
            services.outboxSync.kick()
            await refreshHealthData()
            await services.syncHealthIfDue()
        } catch {
            loginError = error.localizedDescription
        }
    }

    /// Log out: have the server forget this phone's token, then forget it
    /// here. When the server can't be told the token is kept, so that it
    /// isn't left working with nobody holding it; it can always be revoked
    /// in the account settings on the web.
    func logout() async {
        let snapshot = settings.snapshot
        guard snapshot.isConfigured else { return }
        loginBusy = true
        defer { loginBusy = false }
        do {
            try await TasksClient.revokeToken(serverUrl: snapshot.serverUrl, apiToken: snapshot.apiToken)
            settings.saveServerConfig(url: snapshot.serverUrl, token: "")
            loginError = nil
        } catch {
            loginError = error.localizedDescription
        }
    }

    // MARK: Activities

    func openActivitySheet(_ keyword: String? = nil) {
        activityError = nil
        activitySheet = ActivitySheet(keyword: keyword)
        Task { await loadActivityKeywords() }
    }

    private func loadActivityKeywords() async {
        let snapshot = settings.snapshot
        guard snapshot.isConfigured else {
            activityError = notConfiguredMessage
            return
        }
        do {
            activityKeywords = try await TasksClient(snapshot).listActivityKeywords()
        } catch {
            activityError = error.localizedDescription
        }
    }

    /// Record an activity: a new entry of `keyword`'s habit each time (two
    /// gym visits a day are two), its note the hashtag and what was written,
    /// and `values` of the habit's metrics, which the server writes into the
    /// note. The weight shown is read again: it may have been a weigh-in.
    func trackActivity(keyword: String, note: String, values: [String: MetricValue]) async {
        let body = TrackedHabitRequest(
            keyword: keyword,
            // The moment of the tap, so the entry lands on today.
            published: IsoTime.string(),
            note: activityNote(keyword: keyword, note: note),
            values: values
        )
        if await postActivity(body) { await refreshHealthData() }
    }

    /// Send an activity; closes the sheet when it worked.
    private func postActivity(_ body: TrackedHabitRequest) async -> Bool {
        guard !activitySaving else { return false }
        let snapshot = settings.snapshot
        guard snapshot.isConfigured else {
            activityError = notConfiguredMessage
            return false
        }
        activitySaving = true
        activityError = nil
        defer { activitySaving = false }
        do {
            try await TasksClient(snapshot).trackHabitValues(body)
            activitySheet = nil
            return true
        } catch {
            activityError = error.localizedDescription
            return false
        }
    }
}

let notConfiguredMessage = "Set the server URL and log in from Settings first."

/// The server's login page in a browser sheet over the app. It shares
/// Safari's cookies, so a user logged in there is logged in here.
@MainActor
final class WebLogin: NSObject, ASWebAuthenticationPresentationContextProviding {

    private var session: ASWebAuthenticationSession?

    /// Open `url` and wait for the browser to be sent to a URL of
    /// `callbackScheme`, which is returned. Throws when the user closes the
    /// sheet.
    func open(_ url: URL, callbackScheme: String) async throws -> URL {
        try await withCheckedThrowingContinuation { continuation in
            let session = ASWebAuthenticationSession(url: url, callbackURLScheme: callbackScheme) { @Sendable callback, error in
                if let callback {
                    continuation.resume(returning: callback)
                } else {
                    continuation.resume(throwing: error ?? URLError(.cancelled))
                }
            }
            session.presentationContextProvider = self
            self.session = session
            session.start()
        }
    }

    func presentationAnchor(for session: ASWebAuthenticationSession) -> ASPresentationAnchor {
        let scenes = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }
        return scenes.compactMap(\.keyWindow).first ?? ASPresentationAnchor()
    }
}
