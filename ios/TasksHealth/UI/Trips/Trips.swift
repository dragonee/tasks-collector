import Observation
import SwiftUI

@MainActor
@Observable
final class TripsModel {

    private static let pageSize = 20

    @ObservationIgnored private unowned let services: AppServices
    @ObservationIgnored private var historyPage = 1
    @ObservationIgnored private var openedOnce = false

    private(set) var active: [TripSummary] = []
    private(set) var history: [TripSummary] = []
    private(set) var totalHistory = 0
    private(set) var loading = false
    var error: String?
    private(set) var configured = false

    /// The trips opened on top of the list, by id.
    var path: [Int64] = []

    init(_ services: AppServices) {
        self.services = services
    }

    /// Start a trip and open it. Starting one turns location tracking on,
    /// so the permission it needs is asked for first; the trip starts
    /// whatever the user answers.
    func startTrip() async {
        guard let snapshot = configuredSnapshot() else { return }
        _ = await services.location.requestPermission()
        loading = true
        defer { loading = false }
        do {
            let story = try await TasksClient(snapshot).startTrip(TripStartRequest()).story
            path = [story.id]
            // Begin recording the breadcrumb trail of this trip.
            services.tracker.start(story.id)
            await reload()
        } catch {
            self.error = error.localizedDescription
        }
    }

    func loadMoreHistory() async {
        guard let snapshot = configuredSnapshot() else { return }
        loading = true
        defer { loading = false }
        do {
            let page = try await TasksClient(snapshot).listTrips(page: historyPage + 1, pageSize: Self.pageSize)
            historyPage += 1
            history += page.history
            totalHistory = page.totalHistory
        } catch {
            self.error = error.localizedDescription
        }
    }

    func reload() async {
        let snapshot = services.settings.snapshot
        configured = snapshot.isConfigured
        guard snapshot.isConfigured else {
            active = []
            history = []
            totalHistory = 0
            return
        }
        loading = true
        defer { loading = false }
        do {
            let page = try await TasksClient(snapshot).listTrips(page: 1, pageSize: Self.pageSize)
            historyPage = 1
            active = page.active
            history = page.history
            totalHistory = page.totalHistory
            error = nil
            // Follow the server: a trip stopped elsewhere (on the web) turns
            // the recorder off; an active one keeps it on.
            services.tracker.reconcile(activeIds: page.active.map(\.id))
            // The first time only, with exactly one active trip, go straight
            // into it. Later the user stays on the list, so going back works.
            if !openedOnce, page.active.count == 1, path.isEmpty {
                path = [page.active[0].id]
            }
            openedOnce = true
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func configuredSnapshot() -> SettingsSnapshot? {
        let snapshot = services.settings.snapshot
        configured = snapshot.isConfigured
        if !snapshot.isConfigured { error = notConfiguredMessage }
        return snapshot.isConfigured ? snapshot : nil
    }
}

struct TripsView: View {

    @Bindable var model: TripsModel
    let services: AppServices

    var body: some View {
        NavigationStack(path: $model.path) {
            List {
                if let error = model.error {
                    ErrorBanner(message: error) { model.error = nil }
                        .listRowSeparator(.hidden)
                }
                if model.configured {
                    Button("Start a trip") { Task { await model.startTrip() } }
                        .buttonStyle(.borderedProminent)
                        .frame(maxWidth: .infinity)
                        .listRowSeparator(.hidden)

                    if !model.active.isEmpty {
                        Section("Active") {
                            ForEach(model.active) { TripRow(trip: $0) }
                        }
                    }
                    Section("Past trips") {
                        if model.history.isEmpty {
                            Text("No past trips yet.").foregroundStyle(.secondary)
                        } else {
                            ForEach(model.history) { TripRow(trip: $0) }
                            if model.history.count < model.totalHistory {
                                Button("Load more") { Task { await model.loadMoreHistory() } }
                                    .frame(maxWidth: .infinity)
                            }
                        }
                    }
                }
            }
            .listStyle(.plain)
            .refreshable { await model.reload() }
            .overlay {
                if !model.configured { EmptyState(text: notConfiguredMessage) }
            }
            .navigationTitle("Trips")
            .navigationBarTitleDisplayMode(.inline)
            .navigationDestination(for: Int64.self) { storyId in
                TripDetailView(services: services, storyId: storyId)
            }
        }
        .task { await model.reload() }
    }
}

private struct TripRow: View {
    let trip: TripSummary

    var body: some View {
        NavigationLink(value: trip.id) {
            VStack(alignment: .leading, spacing: 2) {
                Text(trip.title)
                Text(formatTripRange(startedIso: trip.started, stoppedIso: trip.stopped))
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
        }
    }
}
