import PhotosUI
import SwiftUI

struct TripDetailView: View {

    @State private var model: TripDetailModel
    @State private var photoPickerOpen = false
    @State private var pickedPhotos: [PhotosPickerItem] = []
    @State private var titleDraft = ""

    init(services: AppServices, storyId: Int64) {
        _model = State(initialValue: TripDetailModel(services, storyId: storyId))
    }

    var body: some View {
        @Bindable var model = model
        let timeline = model.timeline
        // The time alone, or with its date: once for the whole list, by
        // whether the trip spans more than one local day.
        let timeStyle = model.story.map { story in
            EventTimeStyle.pick(
                startedIso: story.started,
                stoppedIso: story.stopped,
                eventIsos: timeline.map(\.publishedIso)
            )
        } ?? .time

        List {
            Section {
                if let story = model.story {
                    Text(formatTripRange(startedIso: story.started, stoppedIso: story.stopped))
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
                if let error = model.error {
                    ErrorBanner(message: error) { model.error = nil }
                }
                SyncBadge(pending: model.pending, syncing: model.syncing, onRetryAll: model.retryAllFailed)
            }
            .listRowSeparator(.hidden)

            ForEach(timeline) { row in
                switch row {
                case .synced(let event):
                    EventRow(event: event, time: timeStyle.format(event.published), onOpenPhoto: model.openPhoto)
                case .pending(let item):
                    PendingRow(
                        item: item,
                        time: timeStyle.format(item.published),
                        syncing: model.syncing,
                        photoFile: model.pendingPhotoFile(item),
                        onRetry: { model.retry(item) },
                        onDiscard: { model.discard(item) }
                    )
                }
            }
        }
        .listStyle(.plain)
        .refreshable { await model.refresh() }
        .overlay {
            if timeline.isEmpty && !model.loading {
                EmptyState(text: "No notes yet — tap + to record one.")
            }
        }
        .navigationTitle(model.story?.title ?? "")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            if let story = model.story {
                // A stopped trip takes no new entries.
                if story.stopped == nil {
                    ToolbarItem(placement: .primaryAction) {
                        Menu {
                            Button("Add note", systemImage: "note.text") { model.openAddNote() }
                            Button("Add photo", systemImage: "photo") { photoPickerOpen = true }
                        } label: {
                            Label("Add note or photo", systemImage: "plus")
                        }
                    }
                }
                ToolbarItem(placement: .secondaryAction) {
                    Button("Rename", systemImage: "pencil") {
                        titleDraft = story.title
                        model.renameOpen = true
                    }
                }
                ToolbarItem(placement: .secondaryAction) {
                    Button("Share", systemImage: "square.and.arrow.up") { model.shareSheetOpen = true }
                }
                if story.stopped == nil {
                    ToolbarItem(placement: .secondaryAction) {
                        Button(
                            model.trackingPaused ? "Resume location tracking" : "Pause location tracking",
                            systemImage: model.trackingPaused ? "location" : "location.slash",
                            action: model.toggleTracking
                        )
                    }
                    ToolbarItem(placement: .secondaryAction) {
                        Button("Stop trip", systemImage: "stop.circle") { model.stopSheetOpen = true }
                    }
                }
            }
        }
        .task { await model.refresh() }
        .task { await model.followOutbox() }
        // One photo opens the sheet for it; two or more are sent straight
        // away, each with its location from the track.
        .photosPicker(isPresented: $photoPickerOpen, selection: $pickedPhotos, matching: .images)
        .onChange(of: pickedPhotos) { _, items in
            guard !items.isEmpty else { return }
            pickedPhotos = []
            model.picked(items)
        }
        .sheet(isPresented: $model.noteSheetOpen) {
            AddNoteSheet(gps: model.gps, onGrantLocation: model.grantLocation, onSend: model.sendNote)
        }
        .sheet(isPresented: $model.photoSheetOpen, onDismiss: model.closeAddPhoto) {
            AddPhotoSheet(
                photo: model.selectedPhoto,
                gps: model.gps,
                onGrantLocation: model.grantLocation,
                onSend: model.sendPhoto
            )
        }
        .sheet(isPresented: $model.stopSheetOpen) {
            if let story = model.story {
                StopTripSheet(startedIso: story.started, onConfirm: model.stop)
            }
        }
        .sheet(isPresented: $model.shareSheetOpen) {
            ShareTripSheet(
                share: model.share,
                busy: model.shareBusy,
                onCreate: model.createShare,
                onUnshare: model.unshare
            )
        }
        .alert("Rename trip", isPresented: $model.renameOpen) {
            TextField("Title", text: $titleDraft)
            Button("Rename") { model.rename(to: titleDraft) }
            Button("Cancel", role: .cancel) {}
        }
        .fullScreenCover(item: $model.viewer) { viewer in
            PhotoViewer(url: viewer.url)
        }
    }
}

private struct SyncBadge: View {
    let pending: [OutboxItem]
    let syncing: Bool
    let onRetryAll: () -> Void

    var body: some View {
        let waiting = pending.count { !$0.failedPermanently }
        let failed = pending.count(where: \.failedPermanently)
        if waiting > 0 {
            Text(syncing ? "Syncing \(waiting)…" : "\(waiting) waiting to sync")
                .font(.footnote)
                .foregroundStyle(.secondary)
        }
        if failed > 0 {
            HStack {
                Text("\(failed) failed to sync")
                    .font(.footnote)
                    .foregroundStyle(.red)
                    .frame(maxWidth: .infinity, alignment: .leading)
                Button("Retry all", action: onRetryAll).buttonStyle(.borderless)
            }
        }
    }
}

/// The original of a photo, whole. A tap puts it away.
private struct PhotoViewer: View {
    let url: URL
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()
            AsyncImage(url: url) { image in
                image.resizable().scaledToFit()
            } placeholder: {
                ProgressView().tint(.white)
            }
        }
        .onTapGesture { dismiss() }
    }
}

/// The text of a note or photo, with a pin that opens its location in Maps.
private struct CommentLine: View {
    let note: ParsedTripNote
    @Environment(\.openURL) private var openURL

    var body: some View {
        if !note.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || note.poi != nil {
            HStack(alignment: .top) {
                Text(note.text).frame(maxWidth: .infinity, alignment: .leading)
                if let url = note.poi?.mapsUrl {
                    Button {
                        openURL(url)
                    } label: {
                        Image(systemName: "mappin.and.ellipse")
                    }
                    .buttonStyle(.borderless)
                    .accessibilityLabel("Open location in Maps")
                }
            }
        }
    }
}

private struct EventRow: View {
    let event: TripEvent
    let time: String
    let onOpenPhoto: (Int64) -> Void

    var body: some View {
        // A journal's and a photo's comment may start with a #poi line: it
        // becomes the pin, and the rest the text.
        let note = parseTripNote(event.comment ?? "")
        VStack(alignment: .leading, spacing: 6) {
            Text(time).font(.caption).foregroundStyle(.secondary)
            switch event.type {
            case "journal":
                CommentLine(note: note)
            case "photo":
                Button {
                    onOpenPhoto(event.id)
                } label: {
                    if let thumbnail = event.thumbnailUrl.flatMap(URL.init(string:)) {
                        AsyncImage(url: thumbnail) { image in
                            image.resizable().scaledToFit()
                        } placeholder: {
                            ProgressView().frame(height: 120)
                        }
                        .frame(maxWidth: 240, maxHeight: 240)
                    } else {
                        // No thumbnail yet: pulling to refresh brings it.
                        Text("Processing photo…")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                            .frame(width: 240, height: 120)
                            .background(Color.secondary.opacity(0.1))
                    }
                }
                .buttonStyle(.plain)
                .frame(maxWidth: .infinity, alignment: .trailing)
                CommentLine(note: note)
            default:
                Text(event.type)
            }
        }
    }
}

/// A note or photo still queued. Laid out like `EventRow`, so the timeline
/// reads as one, with the photo from the outbox's file and a line saying
/// how its sync stands (and Retry / Discard once it has failed).
private struct PendingRow: View {
    let item: OutboxItem
    let time: String
    let syncing: Bool
    let photoFile: URL?
    let onRetry: () -> Void
    let onDiscard: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(time).font(.caption).foregroundStyle(.secondary)
            if item.isPhoto, let photoFile {
                LocalImage(source: .file(photoFile))
                    .frame(maxWidth: 240, maxHeight: 240)
                    .frame(maxWidth: .infinity, alignment: .trailing)
            }
            CommentLine(note: parseTripNote(item.comment))
            if item.failedPermanently {
                Text("Couldn't sync: \(item.lastError ?? "")").font(.caption).foregroundStyle(.red)
                HStack(spacing: 16) {
                    Button("Retry", action: onRetry)
                    Button("Discard", role: .destructive, action: onDiscard)
                }
                .buttonStyle(.borderless)
            } else {
                Text(syncing ? "Syncing…" : "Waiting to sync").font(.caption).foregroundStyle(.secondary)
            }
        }
    }
}

struct AddNoteSheet: View {
    let gps: GpsState
    let onGrantLocation: () -> Void
    let onSend: (_ text: String, _ includeLocation: Bool) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var draft = ""

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    GpsStatusBlock(state: gps, onGrantLocation: onGrantLocation)
                    NoteField(placeholder: "What's going on?", text: $draft)
                }
                // "Send" attaches no location; this is the explicit choice,
                // on only when a fix is ready.
                Section {
                    Button("Save with location") { onSend(draft, true) }
                        .disabled(gps.fix == nil)
                }
            }
            .navigationTitle("Add a note")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Send") { onSend(draft, false) }
                        .disabled(draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
            }
        }
        .presentationDetents([.medium, .large])
    }
}

/// Picks the moment a trip ended, so a trip the user forgot to stop can be
/// closed at the time they got home rather than whenever they next opened
/// the app.
///
/// Opens on now, so confirming straight away is the plain "stop it now". The
/// picker offers only moments from the trip's start to now; the server
/// enforces the same window.
struct StopTripSheet: View {
    let startedIso: String
    let onConfirm: (Date) -> Void

    @Environment(\.dismiss) private var dismiss
    /// When the sheet opened: the latest the trip can have ended.
    @State private var now: Date
    @State private var chosen: Date

    init(startedIso: String, onConfirm: @escaping (Date) -> Void) {
        self.startedIso = startedIso
        self.onConfirm = onConfirm
        // One reading of the clock for both: two would put the choice a
        // moment after "now", and out of range.
        let now = Date()
        _now = State(initialValue: now)
        _chosen = State(initialValue: now)
    }

    /// The start of the minute `date` is in. The picker works in whole
    /// minutes, so a trip started within this minute would otherwise count
    /// as ending before it began.
    private static func minute(_ date: Date) -> Date {
        Date(timeIntervalSinceReferenceDate: (date.timeIntervalSinceReferenceDate / 60).rounded(.down) * 60)
    }

    /// The moment to end the trip at: now while the picker is on the
    /// current minute, else the minute picked (not before the start).
    private func ending(_ started: Date) -> Date {
        Self.minute(chosen) == Self.minute(now) ? Date() : max(chosen, started)
    }

    var body: some View {
        let started = min(IsoTime.parse(startedIso) ?? .distantPast, now)
        let valid = chosen >= Self.minute(started) && chosen <= now
        NavigationStack {
            Form {
                Section {
                    DatePicker("Ended at", selection: $chosen, in: Self.minute(started)...now)
                } footer: {
                    Text("The trip ends at this moment. Change it if you got back earlier and forgot to stop it.")
                }
                if !valid {
                    Text("Pick a moment between the start of the trip and now.")
                        .font(.footnote)
                        .foregroundStyle(.red)
                }
            }
            .navigationTitle("Stop trip")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Stop trip") { onConfirm(ending(started)) }.disabled(!valid)
                }
            }
        }
        .presentationDetents([.medium])
    }
}

/// The public link of a trip. Stays open across making and taking back the
/// link, so the user sees it change: not shared (what a link does, and
/// "Create link"), or shared (the URL, with copy / share / unshare).
struct ShareTripSheet: View {
    let share: TripShare?
    let busy: Bool
    let onCreate: () -> Void
    let onUnshare: () -> Void

    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            Form {
                if let share {
                    Section {
                        Text(share.url).font(.footnote).textSelection(.enabled)
                        Button("Copy link") { UIPasteboard.general.string = share.url }
                        if let url = URL(string: share.url) {
                            ShareLink("Share…", item: url)
                        }
                    } footer: {
                        Text("Anyone with this link can view the trip.")
                    }
                    Section {
                        Button("Unshare", role: .destructive, action: onUnshare).disabled(busy)
                    }
                } else {
                    Section {
                        Button("Create link", action: onCreate).disabled(busy)
                    } footer: {
                        Text("Create a public link that anyone can use to view this trip.")
                    }
                }
            }
            .navigationTitle("Share trip")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Close") { dismiss() } }
            }
        }
        .presentationDetents([.medium])
    }
}
