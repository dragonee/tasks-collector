import Foundation
import HealthKit

/// Pushes the health metrics of the last days to the server: one
/// `health-metrics` habit entry per day (the server keeps one per day and
/// updates it), and one `workout` entry per bike ride.
///
/// An actor with one sync at a time: a second caller waits for the one under
/// way. Two at once would both see a ride as not posted yet and post it
/// twice.
actor HealthSync {

    static let habitKeyword = "health-metrics"
    static let workoutKeyword = "workout"

    /// Days synced each time, today included. Watches fill in earlier days
    /// late, so a day can still change after it is over.
    static let windowDays = 7

    private let settings: Settings
    private let health: HealthRepository
    private var underWay: Task<Void, Never>?

    init(settings: Settings, health: HealthRepository) {
        self.settings = settings
        self.health = health
    }

    func run() async {
        if let underWay {
            await underWay.value
            return
        }
        let sync = Task { await self.sync() }
        underWay = sync
        await sync.value
        underWay = nil
    }

    private func sync() async {
        let snapshot = await settings.snapshot
        guard snapshot.isConfigured else {
            await settings.recordSyncFailure("Server URL or API token not set")
            return
        }
        guard await health.accessRequested() else {
            await settings.recordSyncFailure("Health access not granted")
            return
        }
        do {
            let api = try TasksClient(snapshot)
            let today = Day.today()
            var posted = await settings.syncedBikeSessionIds

            // Oldest first.
            for offset in (0..<Self.windowDays).reversed() {
                let day = today.adding(days: -offset)
                let metrics = try await health.aggregateDay(day)
                try await api.trackHabit(
                    TrackHabitRequest(
                        keyword: Self.habitKeyword,
                        date: day.iso,
                        note: NoteFormatter.format(metrics)
                    )
                )
                for ride in try await health.bikeSessions(day) where !posted.contains(ride.id) {
                    try await api.trackHabitText(
                        TrackHabitTextRequest(
                            text: NoteFormatter.formatBikeRide(
                                keyword: Self.workoutKeyword,
                                durationMinutes: ride.durationMinutes
                            ),
                            // When the ride started, so the entry lands on
                            // the day of the ride, not of the sync.
                            published: IsoTime.string(ride.start)
                        )
                    )
                    // Remembered at once, so a sync that fails further on
                    // doesn't post the ride again next time.
                    posted.insert(ride.id)
                    await settings.addSyncedBikeSessionId(ride.id)
                }
            }
            await settings.recordSyncSuccess()
        } catch let error as HKError where error.code == .errorDatabaseInaccessible {
            // The phone is locked: health data can't be read until it is
            // unlocked. Not a failure to tell the user about.
        } catch {
            await settings.recordSyncFailure(error.localizedDescription)
        }
    }
}
