import CoreLocation
import UIKit

/// Records a breadcrumb trail while a trip is active.
///
/// Location updates go on in the background on a while-in-use permission:
/// they are started while the app is in front and the app has the location
/// background mode, so iOS keeps delivering them (with its blue indicator)
/// and no "always" permission is needed. A sample is kept every
/// `activeInterval` while the app is in front and every `idleInterval`
/// otherwise, for a useful trail that doesn't drain the battery. When it
/// runs is up to `TripTracker`.
@MainActor
final class TripLocationRecorder: NSObject, CLLocationManagerDelegate {

    private static let activeInterval: TimeInterval = 30
    private static let idleInterval: TimeInterval = 120

    private let manager = CLLocationManager()
    private let store: BreadcrumbStore
    private var running = false
    private var lastKept: Date?

    init(store: BreadcrumbStore) {
        self.store = store
        super.init()
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyHundredMeters
        manager.pausesLocationUpdatesAutomatically = false
    }

    func start() {
        guard !running else { return }
        running = true
        manager.allowsBackgroundLocationUpdates = true
        manager.showsBackgroundLocationIndicator = true
        manager.startUpdatingLocation()
    }

    func stop() {
        guard running else { return }
        running = false
        lastKept = nil
        manager.stopUpdatingLocation()
        manager.allowsBackgroundLocationUpdates = false
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        let crumbs = locations.map { location in
            Breadcrumb(
                t: location.timestamp.epochMillis,
                lat: location.coordinate.latitude,
                lng: location.coordinate.longitude,
                acc: location.horizontalAccuracy >= 0 ? Float(location.horizontalAccuracy) : nil
            )
        }
        Task { @MainActor in self.keep(crumbs) }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        // No fix right now; the next one that comes is recorded.
    }

    private func keep(_ crumbs: [Breadcrumb]) {
        guard running else { return }
        let inFront = UIApplication.shared.applicationState == .active
        let interval = inFront ? Self.activeInterval : Self.idleInterval
        for crumb in crumbs {
            let at = Date(epochMillis: crumb.t)
            if let lastKept, at.timeIntervalSince(lastKept) < interval { continue }
            store.append(crumb)
            lastKept = at
        }
    }
}

/// Runs the `TripLocationRecorder` off the set of trips tracked on this
/// phone (`Settings.trackedStoryIds`): it records whenever that set is not
/// empty and tracking isn't paused. When the set empties (the last active
/// trip stopped) recording stops and the breadcrumb log is cleared.
///
/// Pausing is apart from the trip: it stops sampling and keeps the trail, so
/// resuming goes on with the same log. The trail is dropped only when the
/// last trip finishes, never on pause.
@MainActor
final class TripTracker {

    private let settings: Settings
    private let location: LocationProvider
    private let recorder: TripLocationRecorder
    private let store: BreadcrumbStore

    init(settings: Settings, location: LocationProvider, store: BreadcrumbStore) {
        self.settings = settings
        self.location = location
        self.store = store
        recorder = TripLocationRecorder(store: store)
    }

    /// Begin tracking a trip that was just started.
    func start(_ storyId: Int64) {
        settings.setTrackedStoryIds(settings.trackedStoryIds.union([storyId]))
        ensure()
    }

    /// Stop tracking a trip that was just stopped.
    func stop(_ storyId: Int64) {
        settings.setTrackedStoryIds(settings.trackedStoryIds.subtracting([storyId]))
        ensure()
    }

    /// Stop sampling without ending the trip or dropping the trail.
    func pause() {
        settings.setTrackingPaused(true)
        ensure()
    }

    /// Sample again, going on with the trail there is.
    func resume() {
        settings.setTrackingPaused(false)
        ensure()
    }

    /// Follow the server's active trips (one stopped on the web turns
    /// tracking off; one started elsewhere turns it on). Called after the
    /// trips are fetched.
    func reconcile(activeIds: [Int64]) {
        settings.setTrackedStoryIds(Set(activeIds))
        ensure()
    }

    /// Record again when the app is opened, if trips were being tracked
    /// (the recorder doesn't outlive the app), or once the user has granted
    /// the location.
    func resumeIfNeeded() {
        ensure()
    }

    private func ensure() {
        if settings.trackedStoryIds.isEmpty {
            // No active trip owns the trail any more: stop and drop it. The
            // pause is over too, so the next trip starts sampling.
            recorder.stop()
            store.clear()
            if settings.trackingPaused { settings.setTrackingPaused(false) }
            return
        }
        if settings.trackingPaused {
            recorder.stop()
            return
        }
        // Without the permission there is nothing to record. The tracked ids
        // stay: the next call after the user grants it starts the recorder.
        guard location.hasPermission else { return }
        recorder.start()
    }
}
