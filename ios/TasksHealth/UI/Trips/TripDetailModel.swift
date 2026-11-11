import Foundation
import Observation
import PhotosUI
import SwiftUI

@MainActor
@Observable
final class TripDetailModel {

    /// One row of the timeline: an event the server has, or one still queued.
    enum TimelineRow: Identifiable {
        case synced(TripEvent)
        case pending(OutboxItem)

        var publishedIso: String {
            switch self {
            case .synced(let event): event.published
            case .pending(let item): item.published
            }
        }

        var id: String {
            switch self {
            case .synced(let event): "s-\(event.type)-\(event.id)"
            case .pending(let item): "p-\(item.id)"
            }
        }
    }

    /// The original of a photo, open to look at.
    struct Viewer: Identifiable {
        let url: URL
        var id: URL { url }
    }

    @ObservationIgnored private unowned let services: AppServices
    let storyId: Int64

    private(set) var story: TripSummary?
    private(set) var events: [TripEvent] = []
    /// Trip writes still in the outbox (waiting, syncing or failed).
    private(set) var pending: [OutboxItem] = []
    /// True while the outbox is being drained.
    private(set) var syncing = false
    private(set) var loading = false
    var error: String?

    var noteSheetOpen = false
    var photoSheetOpen = false
    private(set) var selectedPhoto: PickedPhoto?
    /// Where finding a location stands, for the sheet that is open.
    private(set) var gps: GpsState = .idle

    var viewer: Viewer?
    var renameOpen = false
    var stopSheetOpen = false
    var shareSheetOpen = false
    /// The trip's public share link (nil: not shared).
    private(set) var share: TripShare?
    /// True while sharing or unsharing is being settled with the server.
    private(set) var shareBusy = false

    init(_ services: AppServices, storyId: Int64) {
        self.services = services
        self.storyId = storyId
    }

    private var outbox: Outbox { services.outbox }

    /// Location tracking is one for all trips (see `Settings.trackingPaused`).
    var trackingPaused: Bool { services.settings.trackingPaused }

    /// Server events and queued items as one list, newest first, so a note
    /// or photo just queued shows before it has reached the server.
    var timeline: [TimelineRow] {
        (events.map(TimelineRow.synced) + pending.map(TimelineRow.pending))
            .map { (row: $0, at: IsoTime.parse($0.publishedIso) ?? .distantPast) }
            .enumerated()
            .sorted { ($0.element.at, $1.offset) > ($1.element.at, $0.offset) }
            .map(\.element.row)
    }

    /// Follow the outbox for as long as the screen is up: keep the pending
    /// list fresh, say when it is syncing, and fetch the events again when a
    /// drain ends (so what was sent turns from pending into real rows).
    func followOutbox() async {
        var wasRunning = false
        for await running in services.outboxSync.states() {
            syncing = running
            await refreshPending()
            if wasRunning && !running { await reload() }
            wasRunning = running
        }
    }

    func refresh() async {
        await reload()
        await refreshPending()
    }

    // MARK: Notes

    /// Open the note sheet and look for a live fix (a note is of "now").
    func openAddNote() {
        noteSheetOpen = true
        gps = .waiting
        Task {
            let found = await services.location.liveState()
            if noteSheetOpen { gps = found }
        }
    }

    func grantLocation() {
        Task {
            gps = .waiting
            let found = await services.location.grantThenLiveState()
            // The trail may be recorded now, too.
            services.tracker.resumeIfNeeded()
            if noteSheetOpen || photoSheetOpen { gps = found }
        }
    }

    /// Queue a note. `includeLocation` is the "Save with location" choice:
    /// plain "Send" attaches no `#poi`, so a location lands only on the
    /// notes it is wanted on.
    func sendNote(text: String, includeLocation: Bool) {
        guard let story, story.stopped == nil else { return }
        let comment = composeComment(fix: includeLocation ? gps.fix : nil, text: text)
        // A note needs something in it: without a location line, some text.
        guard !comment.isEmpty else { return }
        let published = IsoTime.string()
        noteSheetOpen = false
        gps = .idle

        // Queued here and delivered by the outbox, now or when there is a
        // connection; the row shows at once.
        Task {
            _ = await outbox.enqueueNote(storyId: story.id, comment: comment, published: published)
            await refreshPending()
            services.outboxSync.kick()
        }
    }

    // MARK: Photos

    /// Photos were picked: one opens the sheet for it, several are sent
    /// straight away.
    func picked(_ items: [PhotosPickerItem]) {
        if items.count == 1 {
            openAddPhoto(items[0])
        } else if items.count > 1 {
            sendPhotosDirect(items)
        }
    }

    /// Open the photo sheet for a picked image. Unlike a note's, a photo's
    /// location is the trip's recorded trail at the time the photo was taken
    /// (an old photo gets where it was taken, not where the phone is now) —
    /// never a fresh fix.
    private func openAddPhoto(_ item: PhotosPickerItem) {
        Task {
            do {
                let photo = try await PhotoLoader.load(item)
                selectedPhoto = photo
                photoSheetOpen = true
                let crumbs = await readTrail()
                let taken = photo.takenOrNow
                gps = PhotoLocationResolver.resolve(crumbs, captureMs: taken.epochMillis)
                    .map { .ready($0, source: .track, at: taken) }
                    // Nothing on the track to trust for that time: only a
                    // plain "Send" is offered.
                    ?? .unavailable
            } catch {
                self.error = error.localizedDescription
            }
        }
    }

    func closeAddPhoto() {
        photoSheetOpen = false
        selectedPhoto = nil
        gps = .idle
    }

    /// Queue the photo of the sheet. `includeLocation` as for a note.
    func sendPhoto(text: String, includeLocation: Bool) {
        guard let story, story.stopped == nil, let photo = selectedPhoto else { return }
        let comment = composeComment(fix: includeLocation ? gps.fix : nil, text: text)
        closeAddPhoto()
        Task {
            await enqueue(photo, comment: comment, storyId: story.id)
            await refreshPending()
            services.outboxSync.kick()
        }
    }

    /// Queue several picked photos with no sheet. Each gets its location
    /// from the trip's track at the time it was taken, as the single photo's
    /// "Save with location" does, when there is one to trust.
    private func sendPhotosDirect(_ items: [PhotosPickerItem]) {
        guard let story, story.stopped == nil else { return }
        Task {
            let crumbs = await readTrail()
            // One after another: the outbox's content hash dedups a batch
            // only if each is written before the next is looked at, and this
            // way only one image is in memory at a time.
            for item in items {
                do {
                    let photo = try await PhotoLoader.load(item)
                    let fix = PhotoLocationResolver.resolve(crumbs, captureMs: photo.takenOrNow.epochMillis)
                    await enqueue(photo, comment: composeComment(fix: fix, text: ""), storyId: story.id)
                } catch {
                    self.error = error.localizedDescription
                }
            }
            await refreshPending()
            services.outboxSync.kick()
        }
    }

    private func enqueue(_ photo: PickedPhoto, comment: String, storyId: Int64) async {
        do {
            _ = try await outbox.enqueuePhoto(
                storyId: storyId,
                comment: comment,
                published: IsoTime.string(photo.takenOrNow),
                contentType: photo.contentType,
                bytes: photo.data
            )
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func readTrail() async -> [Breadcrumb] {
        let store = services.breadcrumbs
        return await Task.detached { store.all() }.value
    }

    /// The file a pending photo is in, for its thumbnail.
    func pendingPhotoFile(_ item: OutboxItem) -> URL? {
        outbox.photoFile(item)
    }

    /// Get a fresh link to a photo's original and open it.
    func openPhoto(_ eventId: Int64) {
        Task {
            guard let api = client() else { return }
            do {
                let link = try await api.photoOriginal(eventId: eventId).url
                viewer = URL(string: link).map(Viewer.init)
            } catch {
                self.error = error.localizedDescription
            }
        }
    }

    // MARK: The outbox

    /// Send an item the server refused once more.
    func retry(_ item: OutboxItem) {
        Task {
            var again = item
            again.failedPermanently = false
            again.lastError = nil
            await outbox.update(again)
            await refreshPending()
            services.outboxSync.kick()
        }
    }

    func retryAllFailed() {
        pending.filter(\.failedPermanently).forEach(retry)
    }

    /// Drop a queued item (and its photo) without sending it.
    func discard(_ item: OutboxItem) {
        Task {
            await outbox.remove(item)
            await refreshPending()
        }
    }

    // MARK: The trip

    func toggleTracking() {
        if trackingPaused { services.tracker.resume() } else { services.tracker.pause() }
    }

    /// End the trip at `stoppedAt`, the moment picked in the stop sheet
    /// (now, unless changed). Tracking stops either way: the trail follows
    /// the trip being over, not when it is said to have ended.
    func stop(at stoppedAt: Date) {
        guard let story, story.stopped == nil else { return }
        stopSheetOpen = false
        Task {
            guard let api = client() else { return }
            do {
                try await api.stopTrip(TripStopRequest(storyId: story.id, stopped: IsoTime.string(stoppedAt)))
                services.tracker.stop(story.id)
                await reload()
            } catch {
                self.error = error.localizedDescription
            }
        }
    }

    func rename(to newTitle: String) {
        let title = newTitle.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let story, !title.isEmpty, title != story.title else { return }
        Task {
            guard let api = client() else { return }
            do {
                try await api.updateTrip(TripUpdateRequest(storyId: story.id, title: title))
                await reload()
            } catch {
                self.error = error.localizedDescription
            }
        }
    }

    /// Make (or get) the public share link. Works for a stopped trip too.
    func createShare() {
        guard let story, !shareBusy else { return }
        Task {
            guard let api = client() else { return }
            shareBusy = true
            defer { shareBusy = false }
            do {
                share = try await api.shareTrip(TripStoryIdRequest(storyId: story.id)).share
            } catch {
                self.error = error.localizedDescription
            }
        }
    }

    /// Take the share link back; the old URL stops working for good.
    func unshare() {
        guard let story, !shareBusy else { return }
        Task {
            guard let api = client() else { return }
            shareBusy = true
            defer { shareBusy = false }
            do {
                try await api.revokeTripShare(TripStoryIdRequest(storyId: story.id))
                share = nil
            } catch {
                self.error = error.localizedDescription
            }
        }
    }

    private func reload() async {
        guard let api = client() else { return }
        loading = true
        defer { loading = false }
        do {
            let detail = try await api.tripDetail(storyId: storyId)
            story = detail.story
            events = detail.events
            share = detail.share
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func refreshPending() async {
        pending = await outbox.forStory(storyId)
    }

    private func client() -> TasksClient? {
        let snapshot = services.settings.snapshot
        guard snapshot.isConfigured else {
            error = notConfiguredMessage
            return nil
        }
        do {
            return try TasksClient(snapshot)
        } catch {
            self.error = error.localizedDescription
            return nil
        }
    }
}
