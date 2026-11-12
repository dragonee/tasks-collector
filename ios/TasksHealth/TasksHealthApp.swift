import BackgroundTasks
import SwiftUI

@main
struct TasksHealthApp: App {

    @Environment(\.scenePhase) private var scenePhase
    private let services = AppServices.shared

    var body: some Scene {
        WindowGroup {
            RootView(services: services)
        }
        .onChange(of: scenePhase, initial: true) { _, phase in
            switch phase {
            case .active: services.cameToFront()
            case .background: BackgroundRefresh.schedule()
            default: break
            }
        }
        .backgroundTask(.appRefresh(BackgroundRefresh.identifier)) {
            await AppServices.shared.backgroundRefresh()
        }
    }
}

/// What the app is made of, made once: the stores on disk, what syncs them
/// with the server, and the models of the screens (which live as long as the
/// app does, so a screen is as it was left when the user comes back to it).
@MainActor
final class AppServices {

    static let shared = AppServices()

    /// A health sync runs when the app comes to the front and the last one
    /// is at least this old.
    private static let healthSyncEvery: TimeInterval = 60 * 60

    let settings: Settings
    let outbox: Outbox
    let savedPlans: SavedPlans
    let breadcrumbs: BreadcrumbStore
    let outboxSync: OutboxSync
    let health = HealthRepository()
    let healthSync: HealthSync
    let location = LocationProvider()
    let tracker: TripTracker

    private(set) lazy var main = MainModel(self)
    private(set) lazy var today = TodayModel(self)
    private(set) lazy var addPhoto = AddPhotoModel(self)
    private(set) lazy var trips = TripsModel(self)

    private var lastHealthSync: Date?

    private init() {
        let support = URL.applicationSupportDirectory
        settings = Settings()
        outbox = Outbox(dir: support.appending(path: "outbox"))
        savedPlans = SavedPlans(dir: support.appending(path: "plans"))
        breadcrumbs = BreadcrumbStore(file: support.appending(path: "breadcrumbs.log"))
        outboxSync = OutboxSync(settings: settings, outbox: outbox)
        healthSync = HealthSync(settings: settings, health: health)
        tracker = TripTracker(settings: settings, location: location, store: breadcrumbs)
    }

    /// The app was opened or brought back: deliver what was queued, record
    /// the trip again if one was being tracked, and bring the screens up to
    /// date.
    func cameToFront() {
        outboxSync.kick()
        tracker.resumeIfNeeded()
        Task {
            await main.refresh()
            await refreshSavedPlans()
            await syncHealthIfDue()
        }
    }

    /// Keep today's and tomorrow's plans on the phone, so a plan written on
    /// the web in the evening is on the Today list the next morning, with a
    /// connection or without. Without one now, what is kept stays.
    func refreshSavedPlans() async {
        let snapshot = settings.snapshot
        guard snapshot.isConfigured, let api = try? TasksClient(snapshot) else { return }
        let account = SavedPlans.account(serverUrl: snapshot.serverUrl, apiToken: snapshot.apiToken)
        try? await savedPlans.refresh(api, account: account)
    }

    /// Push the health metrics, unless that was done within the hour.
    func syncHealthIfDue() async {
        if let lastHealthSync, Date().timeIntervalSince(lastHealthSync) < Self.healthSyncEvery { return }
        guard settings.snapshot.isConfigured, await health.accessRequested() else { return }
        lastHealthSync = Date()
        await healthSync.run()
    }

    func syncHealthNow() async {
        lastHealthSync = Date()
        await healthSync.run()
    }

    /// iOS woke the app in the background: sync what can be synced, and ask
    /// to be woken again.
    func backgroundRefresh() async {
        BackgroundRefresh.schedule()
        await refreshSavedPlans()
        await healthSync.run()
        await outboxSync.drainNow()
    }
}

/// The periodic wake-up iOS grants the app while it isn't open: when, and
/// how often, is up to iOS (roughly, as often as the app is used).
enum BackgroundRefresh {

    static let identifier = "org.polybrain.tasks.health.refresh"

    static func schedule() {
        let request = BGAppRefreshTaskRequest(identifier: identifier)
        request.earliestBeginDate = Date(timeIntervalSinceNow: 60 * 60)
        // Refused in the simulator and when the user has turned background
        // refresh off; the app then syncs when it is opened.
        try? BGTaskScheduler.shared.submit(request)
    }
}
