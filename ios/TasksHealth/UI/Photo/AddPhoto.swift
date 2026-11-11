import Observation
import PhotosUI
import SwiftUI

/// The standalone "Add Photo" of the Today screen: a photo queued with no
/// trip, an optional note, and an optional live GPS fix — there is no trip
/// track to go by, so the location is always where the phone is now.
///
/// The photo is queued with no story; `OutboxDrainer` then delivers it
/// through the storyless photo endpoints. A trip photo's upload shows in the
/// trip's timeline; a standalone one has no screen of its own, so how it
/// went is said in a `notice`: after each drain, that the photos are
/// uploaded, or that they are not.
@MainActor
@Observable
final class AddPhotoModel {

    @ObservationIgnored private unowned let services: AppServices

    var sheetOpen = false
    private(set) var selectedPhoto: PickedPhoto?
    private(set) var gps: GpsState = .idle

    /// What to tell the user about an upload; goes away by itself.
    private(set) var notice: String?
    @ObservationIgnored private var noticeGoes: Task<Void, Never>?

    /// Ids of the queued standalone photos whose delivery hasn't been
    /// reported yet.
    @ObservationIgnored private var watched: Set<String> = []

    init(_ services: AppServices) {
        self.services = services
        // After each drain, say what it did to the watched photos: gone from
        // the outbox is delivered, still there is failed (with the error it
        // recorded). Trip items show in the trip's timeline.
        Task { [weak self, outbox = services.outbox, sync = services.outboxSync] in
            let queued = Set(await outbox.standalone().map(\.id))
            self?.watched.formUnion(queued)
            var wasRunning = false
            for await running in sync.states() {
                guard let self else { return }
                if wasRunning && !running { await self.reportDrain() }
                wasRunning = running
            }
        }
    }

    private func reportDrain() async {
        let remaining = await services.outbox.standalone()
        let remainingIds = Set(remaining.map(\.id))
        let delivered = watched.subtracting(remainingIds).count
        if remaining.isEmpty {
            if delivered > 0 {
                say(delivered == 1 ? "Photo uploaded" : "\(delivered) photos uploaded")
            }
        } else if !watched.isEmpty {
            let failed = remaining.first { $0.lastError != nil } ?? remaining[0]
            let willRetry = !remaining.contains(where: \.failedPermanently)
            say("Photo upload failed: \(failed.lastError ?? "unknown error")\(willRetry ? " — will retry" : "")")
        }
        watched = remainingIds
    }

    private func say(_ text: String) {
        notice = text
        noticeGoes?.cancel()
        noticeGoes = Task {
            try? await Task.sleep(for: .seconds(4))
            if !Task.isCancelled { notice = nil }
        }
    }

    /// A photo was picked: open the sheet for it and look for a live fix.
    func open(_ item: PhotosPickerItem) {
        Task {
            do {
                selectedPhoto = try await PhotoLoader.load(item)
            } catch {
                say("Could not save photo: \(error.localizedDescription)")
                return
            }
            sheetOpen = true
            gps = .waiting
            let found = await services.location.liveState()
            if sheetOpen { gps = found }
        }
    }

    func close() {
        sheetOpen = false
        selectedPhoto = nil
        gps = .idle
    }

    func grantLocation() {
        Task {
            gps = .waiting
            let found = await services.location.grantThenLiveState()
            if sheetOpen { gps = found }
        }
    }

    /// Queue the photo with no story. `includeLocation` is the "Save with
    /// location" choice; plain "Send" attaches no `#poi`.
    func send(text: String, includeLocation: Bool) {
        guard let photo = selectedPhoto else { return }
        let comment = composeComment(fix: includeLocation ? gps.fix : nil, text: text)
        // A standalone photo is dated when it is added (now), not when it
        // was taken — unlike a trip photo.
        let published = IsoTime.string()
        close()

        Task {
            do {
                let item = try await services.outbox.enqueuePhoto(
                    storyId: nil,
                    comment: comment,
                    published: published,
                    contentType: photo.contentType,
                    bytes: photo.data
                )
                // Nil: the same image is queued already, and watched.
                if let item {
                    watched.insert(item.id)
                    services.outboxSync.kick()
                }
            } catch {
                say("Could not save photo: \(error.localizedDescription)")
            }
        }
    }
}

/// The sheet a picked photo is sent from, for a trip photo (located by the
/// trip's track) and for a standalone one (located by a live fix).
struct AddPhotoSheet: View {
    let photo: PickedPhoto?
    let gps: GpsState
    let onGrantLocation: () -> Void
    let onSend: (_ text: String, _ includeLocation: Bool) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var draft = ""

    var body: some View {
        NavigationStack {
            Form {
                if let photo {
                    LocalImage(source: .data(photo.data))
                        .frame(maxWidth: .infinity, maxHeight: 240)
                        .listRowInsets(EdgeInsets())
                }
                Section {
                    if case .ready(_, .track, let at) = gps {
                        // The location is the recorded track's, not a live
                        // one: say so, with the time it was matched to.
                        Text("Location from your trip track (\(at.map { Stamp.time($0) } ?? ""))")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    } else {
                        GpsStatusBlock(state: gps, onGrantLocation: onGrantLocation)
                    }
                    NoteField(placeholder: "Add a caption (optional)", text: $draft, lines: 2)
                }
                // "Send" attaches no location; this is the explicit choice,
                // on only when a fix is ready.
                Section {
                    Button("Save with location") { onSend(draft, true) }
                        .disabled(gps.fix == nil)
                }
            }
            .navigationTitle("Add a photo")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) { Button("Send") { onSend(draft, false) } }
            }
        }
    }
}

/// Where finding a location stands, in a line.
struct GpsStatusBlock: View {
    let state: GpsState
    let onGrantLocation: () -> Void

    var body: some View {
        switch state {
        case .idle, .waiting:
            Text("Waiting for GPS…").font(.footnote).foregroundStyle(.secondary)
        case .ready(let fix, _, _):
            Text(String(format: "Location ready (%.5f, %.5f)", fix.lat, fix.lng))
                .font(.footnote)
                .foregroundStyle(.secondary)
        case .denied:
            VStack(alignment: .leading) {
                Text("No location available.").font(.footnote).foregroundStyle(.red)
                Button("Grant location permission", action: onGrantLocation)
            }
        case .unavailable:
            Text("No location available.").font(.footnote).foregroundStyle(.red)
        }
    }
}
