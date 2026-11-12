import PhotosUI
import SwiftUI

struct TodayView: View {

    @Bindable var model: TodayModel
    @Bindable var addPhoto: AddPhotoModel
    let services: AppServices

    @State private var boardPickerOpen = false
    @State private var photoPickerOpen = false
    @State private var pickedPhoto: PhotosPickerItem?

    var body: some View {
        NavigationStack {
            VStack(spacing: 8) {
                DateNavBar(
                    label: model.isToday ? "Today" : Self.dayLabel(model.selectedDate),
                    onPrevious: model.previousDay,
                    onNext: model.nextDay,
                    onToday: model.goToToday
                )
                AddTaskRow(placeholder: "Add a task", enabled: model.configured, onAdd: model.add)
                if let error = model.error {
                    ErrorBanner(message: "Error: \(error)") { model.error = nil }
                }
                if let savedAt = model.savedAt {
                    SavedPlansNotice(savedAt: savedAt)
                }
                SyncStatus(
                    waiting: model.waiting,
                    failed: model.failed,
                    onRetry: model.retrySync,
                    onDiscard: model.discardSync
                )
            }
            .padding(.horizontal, 16)
            .padding(.top, 8)

            list
                .navigationTitle("Tasks Collector")
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    // Hidden until there is a server, like the add row above.
                    if model.configured {
                        ToolbarItem(placement: .primaryAction) { addMenu }
                    }
                }
        }
        .task { await model.reload() }
        .sheet(isPresented: $boardPickerOpen) {
            BoardPickerView(model: BoardPickerModel(services), date: model.selectedDate)
        }
        .photosPicker(isPresented: $photoPickerOpen, selection: $pickedPhoto, matching: .images)
        .onChange(of: pickedPhoto) { _, item in
            guard let item else { return }
            pickedPhoto = nil
            addPhoto.open(item)
        }
        .sheet(isPresented: $addPhoto.sheetOpen, onDismiss: addPhoto.close) {
            AddPhotoSheet(
                photo: addPhoto.selectedPhoto,
                gps: addPhoto.gps,
                onGrantLocation: addPhoto.grantLocation,
                onSend: addPhoto.send
            )
        }
        .sheet(isPresented: $model.habitSheetOpen) {
            TrackHabitSheet(model: model)
        }
        .sheet(item: $model.pendingComplete) { pending in
            switch pending {
            case .addNote:
                JournalNoteSheet(hasActiveTrip: model.activeTrip != nil) { note, toTrip in
                    model.confirmCompletion(note: note, toTrip: toTrip)
                }
            case .completedAction(let task):
                CompletedTaskSheet(
                    taskText: task.shown,
                    onAddAnother: model.confirmAddAnother,
                    onReset: model.confirmReset
                )
            }
        }
    }

    private var addMenu: some View {
        Menu {
            Button("Add Task", systemImage: "list.bullet.indent") { boardPickerOpen = true }
            Button("Add Photo", systemImage: "photo") { photoPickerOpen = true }
            Button("Track Habit", systemImage: "number") { model.openHabitSheet() }
        } label: {
            Label("Add", systemImage: "plus")
        }
    }

    @ViewBuilder
    private var list: some View {
        // Focus mode hides everything but the focused task and the finished
        // ones, so the one thing left to do stands alone (the done list is
        // kept, for heart). The week's plan is "other tasks", and hidden too.
        let focusMode = model.focusedTask != nil
        // What is left of this week's plan: not done yet, wherever that
        // would have been ticked, and not on this day's list already.
        let weekLeft = focusMode ? [] : weekPlanLeft(model.weekPlan, today: model.tasks)
        let shown = focusMode
            ? model.tasks.filter { $0.key == model.focusedTask || $0.done }
            : model.tasks

        List {
            if !weekLeft.isEmpty {
                Section("Plan for this week") {
                    ForEach(weekLeft, id: \.key) { task in
                        Text(task.shown)
                            .foregroundStyle(.secondary)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .contentShape(Rectangle())
                            .contextMenu {
                                Button("Add to today", systemImage: "arrow.down") {
                                    model.addPlanItemToToday(task)
                                }
                            }
                    }
                }
            }
            if !shown.isEmpty {
                Section {
                    ForEach(shown, id: \.key) { task in
                        TaskRow(
                            task: task,
                            focused: task.key == model.focusedTask,
                            // "Copy to today" only while looking at another
                            // day, "Move to tomorrow" only on today.
                            onToday: model.isToday,
                            model: model
                        )
                    }
                }
            }
        }
        .listStyle(.plain)
        .refreshable { await model.reload() }
        .overlay {
            if !model.configured {
                EmptyState(text: notConfiguredMessage)
            } else if model.tasks.isEmpty && weekLeft.isEmpty && !model.loading {
                EmptyState(text: "Nothing on today's plan yet.")
            }
        }
    }

    /// "Wed, May 28"; no year, since most browsing stays within this one.
    private static func dayLabel(_ day: Day) -> String {
        day.start().formatted(.dateTime.weekday(.abbreviated).month(.abbreviated).day())
    }
}

struct EmptyState: View {
    let text: String

    var body: some View {
        Text(text)
            .foregroundStyle(.secondary)
            .multilineTextAlignment(.center)
            .padding(24)
            .allowsHitTesting(false)
    }
}

private struct DateNavBar: View {
    let label: String
    let onPrevious: () -> Void
    let onNext: () -> Void
    let onToday: () -> Void

    var body: some View {
        HStack {
            Button(action: onPrevious) {
                Image(systemName: "chevron.left").frame(width: 44, height: 36)
            }
            .accessibilityLabel("Previous day")
            // Tapping the label goes back to the current day.
            Button(action: onToday) {
                Text(label).font(.headline).frame(maxWidth: .infinity)
            }
            .buttonStyle(.plain)
            Button(action: onNext) {
                Image(systemName: "chevron.right").frame(width: 44, height: 36)
            }
            .accessibilityLabel("Next day")
        }
    }
}

/// A text field with an Add button: on Today for a task of the day, on the
/// board picker for an unscheduled task.
struct AddTaskRow: View {
    let placeholder: String
    let enabled: Bool
    let onAdd: (String) -> Void

    @State private var draft = ""

    var body: some View {
        HStack(spacing: 8) {
            TextField(placeholder, text: $draft)
                .textFieldStyle(.roundedBorder)
                .onSubmit(add)
            Button("Add", action: add)
                .buttonStyle(.borderedProminent)
                .disabled(draft.trimmingCharacters(in: .whitespaces).isEmpty)
        }
        .disabled(!enabled)
    }

    private func add() {
        onAdd(draft)
        draft = ""
    }
}

private struct TaskRow: View {
    let task: PlannedTask
    let focused: Bool
    let onToday: Bool
    let model: TodayModel

    var body: some View {
        HStack(spacing: 12) {
            Button {
                model.requestSetDone(task, done: !task.done)
            } label: {
                Image(systemName: task.done ? "checkmark.square.fill" : "square")
                    .font(.title3)
            }
            .buttonStyle(.plain)
            .foregroundStyle(task.done ? Color.accentColor : .secondary)
            .accessibilityLabel(task.done ? "Done" : "Not done")

            Text(task.shown)
                .strikethrough(task.done)
                .foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .contentShape(Rectangle())
        .contextMenu {
            if onToday {
                Button("Move to tomorrow", systemImage: "arrow.right") { model.moveToTomorrow(task) }
            } else {
                Button("Copy to today", systemImage: "arrow.uturn.backward") { model.copyToToday(task) }
            }
            Button(focused ? "Exit focus mode" : "Enter focus mode", systemImage: "scope") {
                model.toggleFocus(task)
            }
            Button("Remove", systemImage: "trash", role: .destructive) { model.delete(task) }
        }
        // A faint blue wash, so focus mode is plain at a glance.
        .listRowBackground(focused ? Color.blue.opacity(0.12) : nil)
    }
}

/// The server couldn't be asked: the lists are the plans kept from the last
/// fetch. The time alone when that was today.
private struct SavedPlansNotice: View {
    let savedAt: Date

    var body: some View {
        let when = Calendar.current.isDateInToday(savedAt)
            ? savedAt.formatted(date: .omitted, time: .shortened)
            : savedAt.formatted(.dateTime.weekday(.abbreviated).day().month(.abbreviated).hour().minute())
        Text("No connection: the plans as of \(when)")
            .font(.footnote)
            .foregroundStyle(.secondary)
            .frame(maxWidth: .infinity, alignment: .leading)
    }
}

/// What was done to tasks here and is not on the server yet. A call that is
/// sent within a moment says nothing; one that waits (no connection) says so,
/// and one the server refused is listed with Retry / Discard — the list does
/// not show it done.
private struct SyncStatus: View {
    let waiting: Int
    let failed: [OutboxItem]
    let onRetry: (OutboxItem) -> Void
    let onDiscard: (OutboxItem) -> Void

    /// How long a task call may sit in the queue before the screen says so.
    private static let noticeDelay: Duration = .seconds(2)

    @State private var lingering = false

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if lingering && waiting > 0 {
                Text("\(counted(waiting, "change", "changes")) waiting to sync")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            ForEach(failed) { item in
                HStack {
                    Text("Couldn't sync “\(item.task?.task.shown ?? "")”: \(item.lastError ?? "")")
                        .frame(maxWidth: .infinity, alignment: .leading)
                    Button("Retry") { onRetry(item) }
                    Button("Discard") { onDiscard(item) }
                }
                .font(.footnote)
                .buttonStyle(.borderless)
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .background(.red.opacity(0.15), in: RoundedRectangle(cornerRadius: 8))
            }
        }
        .task(id: waiting > 0) {
            lingering = false
            guard waiting > 0 else { return }
            try? await Task.sleep(for: Self.noticeDelay)
            lingering = !Task.isCancelled
        }
    }
}

/// The note that goes with ticking a task: optional, and saved to the active
/// trip when there is one and the user says so.
private struct JournalNoteSheet: View {
    let hasActiveTrip: Bool
    let onSave: (_ note: String, _ toTrip: Bool) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var draft = ""

    var body: some View {
        NavigationStack {
            Form {
                NoteField(placeholder: "Optional", text: $draft)
                if hasActiveTrip {
                    Button("Save to trip") { onSave(draft, true) }
                }
            }
            .navigationTitle("Add a note")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) { Button("Save") { onSave(draft, false) } }
            }
        }
        .presentationDetents([.medium])
    }
}

/// A counted task with all its steps done was tapped: do one more, or take
/// the last one back.
private struct CompletedTaskSheet: View {
    let taskText: String
    let onAddAnother: (String) -> Void
    let onReset: () -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var draft = ""

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Text(taskText).foregroundStyle(.secondary)
                    NoteField(placeholder: "Optional", text: $draft)
                }
                Section {
                    Button("Reset", role: .destructive, action: onReset)
                }
            }
            .navigationTitle("Task complete")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) { Button("Add another") { onAddAnother(draft) } }
            }
        }
        .presentationDetents([.medium])
    }
}

/// Track any habit for the selected day: find one of the user's keywords by
/// typing, and add a note if wanted. Track stays off until the field names a
/// keyword exactly. With no keywords after loading (no habits, or the fetch
/// failed) the sheet offers Retry.
private struct TrackHabitSheet: View {
    let model: TodayModel

    @Environment(\.dismiss) private var dismiss
    @State private var query = ""
    @State private var note = ""

    /// The keyword the field names: typed in full, or picked from the list.
    private var selected: String? {
        let typed = query.trimmingCharacters(in: .whitespaces)
        return model.habitKeywords.first { $0.keyword.caseInsensitiveCompare(typed) == .orderedSame }?.keyword
    }

    /// The keywords containing what is typed; all of them for an empty field.
    private var matching: [HabitKeyword] {
        let typed = query.trimmingCharacters(in: .whitespaces)
        guard !typed.isEmpty else { return model.habitKeywords }
        return model.habitKeywords.filter { $0.keyword.localizedCaseInsensitiveContains(typed) }
    }

    var body: some View {
        NavigationStack {
            Form {
                if model.habitKeywords.isEmpty {
                    Text(model.habitKeywordsLoading ? "Loading habits…" : "No habits available.")
                        .foregroundStyle(.secondary)
                } else {
                    Section {
                        TextField("Habit", text: $query)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                        NoteField(placeholder: "Add a note (optional)", text: $note, lines: 2)
                    }
                    if selected == nil {
                        Section {
                            ForEach(matching) { keyword in
                                Button("#\(keyword.keyword)") { query = keyword.keyword }
                            }
                        }
                    }
                }
                if let error = model.habitError {
                    Text(error).font(.footnote).foregroundStyle(.red)
                }
            }
            .navigationTitle("Track a habit")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }.disabled(model.habitSaving)
                }
                ToolbarItem(placement: .confirmationAction) {
                    // Nothing to track until the list is in: Retry instead.
                    if model.habitKeywords.isEmpty && !model.habitKeywordsLoading {
                        Button("Retry") { Task { await model.loadHabitKeywords(force: true) } }
                    } else {
                        Button("Track") {
                            guard let selected else { return }
                            Task { await model.trackHabit(keyword: selected, note: note) }
                        }
                        .disabled(model.habitSaving || selected == nil)
                    }
                }
            }
        }
        .interactiveDismissDisabled(model.habitSaving)
    }
}
