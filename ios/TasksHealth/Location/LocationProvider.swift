import CoreLocation
import UIKit

/// Asks for the location permission, and for one fresh fix on demand.
@MainActor
final class LocationProvider: NSObject, CLLocationManagerDelegate {

    private let manager = CLLocationManager()
    private var asking: [CheckedContinuation<Bool, Never>] = []

    override init() {
        super.init()
        manager.delegate = self
    }

    var hasPermission: Bool {
        switch manager.authorizationStatus {
        case .authorizedWhenInUse, .authorizedAlways: true
        default: false
        }
    }

    /// The user said no before: asking again shows nothing, and only the
    /// Settings app can change it.
    var isRefused: Bool {
        switch manager.authorizationStatus {
        case .denied, .restricted: true
        default: false
        }
    }

    /// Ask the user, if they haven't been asked yet. Returns whether the app
    /// may use the location.
    func requestPermission() async -> Bool {
        guard manager.authorizationStatus == .notDetermined else { return hasPermission }
        return await withCheckedContinuation { continuation in
            asking.append(continuation)
            manager.requestWhenInUseAuthorization()
        }
    }

    /// A live fix for a sheet that wants one: where finding it ended.
    func liveState() async -> GpsState {
        guard hasPermission else { return .denied }
        return await currentFix().map { .ready($0) } ?? .unavailable
    }

    /// The user tapped "Grant location permission": ask them (or, when they
    /// refused before, show the app's page in Settings, the only place it
    /// can be changed), then find a fix.
    func grantThenLiveState() async -> GpsState {
        if isRefused, let settings = URL(string: UIApplication.openSettingsURLString) {
            await UIApplication.shared.open(settings)
            return .denied
        }
        guard await requestPermission() else { return .denied }
        return await liveState()
    }

    nonisolated func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        Task { @MainActor in self.authorizationChanged() }
    }

    private func authorizationChanged() {
        guard manager.authorizationStatus != .notDetermined else { return }
        let granted = hasPermission
        asking.forEach { $0.resume(returning: granted) }
        asking = []
    }

    /// One fresh fix, or nil when the permission is missing, nothing comes
    /// within `timeout`, or the phone has no location to give. Callers treat
    /// nil as "no GPS" and offer saving without a location.
    func currentFix(timeout: Duration = .seconds(10)) async -> LocationFix? {
        guard hasPermission else { return nil }
        return await withTaskGroup(of: LocationFix?.self) { group in
            group.addTask {
                do {
                    for try await update in CLLocationUpdate.liveUpdates() {
                        guard let location = update.location,
                              location.horizontalAccuracy >= 0,
                              location.timestamp.timeIntervalSinceNow > -30
                        else { continue }
                        return LocationFix(
                            lat: location.coordinate.latitude,
                            lng: location.coordinate.longitude,
                            accuracyMeters: Float(location.horizontalAccuracy)
                        )
                    }
                } catch {}
                return nil
            }
            group.addTask {
                try? await Task.sleep(for: timeout)
                return nil
            }
            let first = await group.next() ?? nil
            group.cancelAll()
            return first
        }
    }
}
