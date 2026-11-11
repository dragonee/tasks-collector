import Foundation
import Network
import UIKit

/// Runs the outbox drain (`OutboxDrainer`): now when asked to, again with a
/// growing wait while something is left to retry, and as soon as the network
/// is back. Everything queued is on disk, so a drain the app didn't live to
/// finish is picked up by the next `kick`.
@MainActor
final class OutboxSync {

    private static let firstRetry: TimeInterval = 30
    private static let longestRetry: TimeInterval = 5 * 60 * 60

    private let settings: Settings
    private let outbox: Outbox
    private let monitor = NWPathMonitor()

    private(set) var running = false
    private var online = true
    /// Asked for while a pass was under way: another follows it.
    private var again = false
    private var failures = 0
    private var retry: Task<Void, Never>?
    private var listeners: [UUID: AsyncStream<Bool>.Continuation] = [:]

    init(settings: Settings, outbox: Outbox) {
        self.settings = settings
        self.outbox = outbox
        monitor.pathUpdateHandler = { @Sendable [weak self] path in
            let online = path.status == .satisfied
            Task { @MainActor in self?.networkChanged(online) }
        }
        monitor.start(queue: .global(qos: .utility))
    }

    /// Whether a pass is running: the current answer, then every change.
    /// A change to "not running" means a pass has just ended, and the queue
    /// is worth looking at again.
    func states() -> AsyncStream<Bool> {
        let id = UUID()
        return AsyncStream { continuation in
            listeners[id] = continuation
            continuation.onTermination = { @Sendable [weak self] _ in
                Task { @MainActor in self?.listeners[id] = nil }
            }
            continuation.yield(running)
        }
    }

    /// Deliver what is queued, now. Called after anything is queued, when
    /// the app comes to the front, and after logging in. While a pass is
    /// running another is lined up behind it; otherwise a wait before a
    /// retry is cut short: a kick from the user should try now.
    func kick() {
        if running {
            again = true
            return
        }
        retry?.cancel()
        retry = nil
        failures = 0
        Task { await pass() }
    }

    /// One pass, waited for: for the background refresh.
    func drainNow() async {
        guard !running else { return }
        await pass()
    }

    private func pass() async {
        // Nothing to do without a server and a token, or without a network;
        // what is queued stays for a later kick.
        let snapshot = settings.snapshot
        guard !running, online, snapshot.isConfigured, let api = try? TasksClient(snapshot) else { return }

        setRunning(true)
        // Let a pass that is under way finish when the app goes to the back.
        let background = UIApplication.shared.beginBackgroundTask(withName: "outbox")
        let leftToRetry = await OutboxDrainer.drain(
            outbox: outbox,
            api: api,
            put: { url, bytes, contentType in
                try await TasksClient.putToPresignedUrl(url, bytes, contentType: contentType)
            }
        )
        UIApplication.shared.endBackgroundTask(background)
        setRunning(false)

        if again {
            again = false
            failures = 0
            await pass()
        } else if leftToRetry {
            retryLater()
        } else {
            failures = 0
        }
    }

    private func retryLater() {
        let wait = min(Self.firstRetry * pow(2, Double(failures)), Self.longestRetry)
        failures += 1
        retry?.cancel()
        retry = Task { [weak self] in
            try? await Task.sleep(for: .seconds(wait))
            guard !Task.isCancelled else { return }
            await self?.pass()
        }
    }

    private func networkChanged(_ online: Bool) {
        let wasOnline = self.online
        self.online = online
        if online && !wasOnline { kick() }
    }

    private func setRunning(_ running: Bool) {
        self.running = running
        listeners.values.forEach { $0.yield(running) }
    }
}
