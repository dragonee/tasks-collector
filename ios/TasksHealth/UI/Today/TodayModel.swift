import Foundation
import Observation

/// The Today list. What is done to a task here is not sent from here: it is
/// queued in the `Outbox` (see `queueOp`) and delivered by `OutboxSync`, now
/// or when there is a connection again. The lists show what the server last
/// said with what is queued on top (`show`), so a tick shows at once and
/// stays through an offline spell. What the server said is kept on the phone
/// (`SavedPlans`): opened without a connection, the list is the day's plans
/// as last fetched.
@MainActor
@Observable
final class TodayModel {

    /// What the user started by tapping a row's checkbox, and the sheet it
    /// opens.
    enum PendingComplete: Identifiable, Equatable {
        /// A tick on an open task: the "Add a note" sheet.
        case addNote(PlannedTask)
        /// A tap on a counted task with all its steps done: Add another /
        /// Reset / Cancel. A plain done task is unticked straight away.
        case completedAction(PlannedTask)

        var task: PlannedTask {
            switch self {
            case .addNote(let task), .completedAction(let task): task
            }
        }

        var id: String { task.key }
    }

    @ObservationIgnored private unowned let services: AppServices

    /// The plans of `agendaDay` as the server last gave them.
    @ObservationIgnored private var agenda = AgendaResponse()
    @ObservationIgnored private var agendaDay: String?
    /// The task calls shown on top of `agenda`.
    @ObservationIgnored private var queue = QueuedTaskOps()
    /// Counts fetches of the plans, so that only the latest one's answer is used.
    @ObservationIgnored private var reloads = 0
    /// Task calls are queued one at a time, in the order they were made.
    @ObservationIgnored private var queueing: Task<Void, Never>?

    /// The selected day's tasks, open ones first, with what is queued for them.
    private(set) var tasks: [PlannedTask] = []
    /// The tasks of the week the selected day is in. Each knows whether it
    /// is done, wherever that was ticked.
    private(set) var weekPlan: [PlannedTask] = []
    /// How many task calls are waiting to be sent.
    private(set) var waiting = 0
    /// Task calls the server refused. They are not shown as done, and stay
    /// queued until the user sends them again or throws them away.
    private(set) var failed: [OutboxItem] = []
    private(set) var loading = false
    var error: String?
    /// When the plans on screen were fetched, if they are the ones kept on
    /// the phone (the server couldn't be asked); nil when they are fresh.
    private(set) var savedAt: Date?
    private(set) var configured = false

    /// The day in view. Every call the screen makes is about this day, so
    /// past days can be looked at and coming ones filled in.
    private(set) var selectedDate = Day.today()

    var pendingComplete: PendingComplete?

    /// Key of the task the user is focusing on, or nil when focus mode is
    /// off. In focus mode the screen shows only this task and the finished
    /// ones. Cleared when the day changes and when the task is gone from the
    /// list (or its "exit focus mode" would be out of reach).
    private(set) var focusedTask: String?

    /// The most recently started active trip, fetched with the list: what
    /// the note sheet's "Save to trip" saves to.
    private(set) var activeTrip: TripSummary?

    /// The habit keywords for the "track a habit" sheet, fetched once: the
    /// user's set rarely changes.
    private(set) var habitKeywords: [HabitKeyword] = []
    var habitSheetOpen = false
    private(set) var habitKeywordsLoading = false
    private(set) var habitSaving = false
    private(set) var habitError: String?

    init(_ services: AppServices) {
        self.services = services
        // Whenever the outbox gets somewhere: see what is left of the queue,
        // and fetch the plans again once calls have been sent.
        Task { [weak self, sync = services.outboxSync] in
            for await _ in sync.states() {
                guard let self else { return }
                if await self.syncQueue() {
                    await self.reload()
                } else {
                    self.show()
                }
            }
        }
    }

    private var settings: Settings { services.settings }
    private var outbox: Outbox { services.outbox }

    var isToday: Bool { selectedDate == .today() }

    func previousDay() { go(to: selectedDate.adding(days: -1)) }

    func nextDay() { go(to: selectedDate.adding(days: 1)) }

    func goToToday() { go(to: .today()) }

    private func go(to day: Day) {
        guard day != selectedDate else { return }
        selectedDate = day
        // A sheet that is open is about a task of the day left behind, and
        // so is the focus.
        pendingComplete = nil
        focusedTask = nil
        Task { await reload() }
    }

    /// Focus on this task, or leave focus mode if it is the one focused on.
    /// Nothing is sent to the server.
    func toggleFocus(_ task: PlannedTask) {
        focusedTask = focusedTask == task.key ? nil : task.key
    }

    /// A task typed in: planned for the selected day. Not written to the board.
    func add(_ text: String) {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        queueOp(.plan, PlannedTask(text: trimmed))
    }

    /// Pull a task of this week's plan into the selected day. It is the same
    /// task on both plans, so ticking it on the day ticks it for the week.
    /// A plain line of the week's plan has no id: the server finds it by its
    /// text and makes it a task on both plans.
    func addPlanItemToToday(_ task: PlannedTask) {
        queueOp(.plan, task)
    }

    /// Put a task on the actual current day as well. Offered only while
    /// looking at some other day, which stays in view.
    func copyToToday(_ task: PlannedTask) {
        queueOp(.plan, task, date: Day.today().iso)
    }

    /// Move a task to tomorrow's plan. It is the same task there, steps done
    /// so far included. Offered only while looking at today.
    func moveToTomorrow(_ task: PlannedTask) {
        queueOp(.move, task, toDate: Day.today().adding(days: 1).iso)
    }

    /// The checkbox was tapped.
    ///
    /// - Ticking an open row opens the note sheet; nothing is queued until
    ///   `confirmCompletion`, and the row stays open till then.
    /// - Unticking a counted task with all its steps done opens the
    ///   completed-task sheet (Add another / Reset / Cancel).
    /// - Unticking a plain task takes it back at once.
    func requestSetDone(_ task: PlannedTask, done: Bool) {
        if done {
            pendingComplete = .addNote(task)
        } else if task.isCountedAndDone {
            pendingComplete = .completedAction(task)
        } else {
            queueOp(.reopen, task)
        }
    }

    /// Save on the note sheet. With `toTrip` the journal entry is linked to
    /// the active trip (a plain save if the trip is gone since the sheet
    /// opened).
    func confirmCompletion(note: String, toTrip: Bool = false) {
        guard case .addNote(let task) = pendingComplete else { return }
        pendingComplete = nil
        // Crossing off the focused task ends focus mode: its one job is done.
        if focusedTask == task.key { focusedTask = nil }
        queueOp(.complete, task, note: note, storyId: toTrip ? activeTrip?.id : nil)
    }

    /// Add another on the completed-task sheet: one more step of a counted
    /// task that has all of them. The note makes a journal entry as a tick's
    /// does.
    func confirmAddAnother(note: String) {
        guard case .completedAction(let task) = pendingComplete else { return }
        pendingComplete = nil
        queueOp(.complete, task, note: note)
    }

    /// Reset on the completed-task sheet: takes back the last step done, and
    /// its line in the reflection.
    func confirmReset() {
        guard case .completedAction(let task) = pendingComplete else { return }
        pendingComplete = nil
        queueOp(.reopen, task)
    }

    /// Take the task off the selected day's plan. The board is left alone,
    /// and a task that was done stays done.
    func delete(_ task: PlannedTask) {
        queueOp(.unplan, task)
    }

    /// Send a task call the server refused once more.
    func retrySync(_ item: OutboxItem) {
        Task {
            var again = item
            again.failedPermanently = false
            again.lastError = nil
            await outbox.update(again)
            await syncQueue()
            show()
            services.outboxSync.kick()
        }
    }

    /// Throw a task call away without sending it.
    func discardSync(_ item: OutboxItem) {
        Task {
            await outbox.remove(item)
            queue.discard(item.id)
            show()
        }
    }

    // MARK: Habits

    /// Open the track-a-habit sheet, with the keywords fetched if they
    /// aren't yet (or the last fetch failed).
    func openHabitSheet() {
        habitError = nil
        habitSheetOpen = true
        if habitKeywords.isEmpty { Task { await loadHabitKeywords() } }
    }

    func loadHabitKeywords(force: Bool = false) async {
        guard !habitKeywordsLoading, force || habitKeywords.isEmpty else { return }
        let snapshot = settings.snapshot
        guard snapshot.isConfigured else {
            habitError = notConfiguredMessage
            return
        }
        habitKeywordsLoading = true
        defer { habitKeywordsLoading = false }
        do {
            habitKeywords = try await TasksClient(snapshot).listHabitKeywords(date: selectedDate.iso)
            habitError = nil
        } catch {
            habitError = error.localizedDescription
        }
    }

    /// Record a habit for the selected day through the idempotent keyword
    /// endpoint (one entry per habit and day). Closes the sheet when it
    /// worked.
    func trackHabit(keyword: String, note: String) async {
        guard !habitSaving else { return }
        let snapshot = settings.snapshot
        guard snapshot.isConfigured else {
            habitError = notConfiguredMessage
            return
        }
        habitSaving = true
        habitError = nil
        defer { habitSaving = false }
        do {
            try await TasksClient(snapshot).trackHabit(
                TrackHabitRequest(
                    keyword: keyword,
                    date: selectedDate.iso,
                    note: note.trimmingCharacters(in: .whitespacesAndNewlines)
                )
            )
            habitSheetOpen = false
        } catch {
            habitError = error.localizedDescription
        }
    }

    // MARK: The lists

    func reload() async {
        let snapshot = settings.snapshot
        configured = snapshot.isConfigured
        guard snapshot.isConfigured else {
            agenda = AgendaResponse()
            agendaDay = nil
            savedAt = nil
            tasks = []
            weekPlan = []
            activeTrip = nil
            return
        }
        let account = SavedPlans.account(serverUrl: snapshot.serverUrl, apiToken: snapshot.apiToken)
        reloads += 1
        let generation = reloads
        let day = selectedDate.iso
        await syncQueue()
        // The calls sent before the plans are asked for are in the answer.
        let covered = queue.sent
        loading = true
        do {
            let api = try TasksClient(snapshot)
            let fetched = try await api.agenda(date: day)
            await services.savedPlans.save(account: account, day: day, agenda: fetched)
            let trip = try await api.listTrips(page: 1, pageSize: 1).active.first
            // A later fetch is on its way: its answer is the one to show.
            guard generation == reloads else { return }
            agenda = fetched
            agendaDay = day
            savedAt = nil
            queue.fetched(covered)
            activeTrip = trip
            error = nil
        } catch {
            guard generation == reloads else { return }
            self.error = error.localizedDescription
            if agendaDay != day {
                // Nothing of this day in hand (no connection): the plans kept
                // from the last fetch, or else an empty list, with what is
                // queued on top.
                let saved = await services.savedPlans.load(account: account, day: day)
                guard generation == reloads else { return }
                agenda = saved?.agenda ?? AgendaResponse()
                agendaDay = day
                savedAt = saved?.savedAt
            }
        }
        loading = false
        // Calls sent while the plans were on their way are not in them.
        if await syncQueue() {
            await reload()
        } else {
            show()
        }
    }

    /// Queue something done to `task` and show it done. `date` is the day of
    /// the plan it is about: the selected day unless said otherwise.
    private func queueOp(
        _ type: TaskOp.Kind,
        _ task: PlannedTask,
        date: String? = nil,
        toDate: String? = nil,
        note: String? = nil,
        storyId: Int64? = nil
    ) {
        let op = TaskOp(
            type: type,
            task: task,
            date: date ?? selectedDate.iso,
            toDate: toDate,
            note: note,
            storyId: storyId
        )
        // The moment of the tap, not of the delivery.
        let published = nowIso()
        let previous = queueing
        queueing = Task {
            await previous?.value
            configured = settings.snapshot.isConfigured
            guard configured else {
                error = notConfiguredMessage
                return
            }
            await outbox.enqueueTask(op, published: published)
            await syncQueue()
            show()
            services.outboxSync.kick()
        }
    }

    /// Take the task calls of the outbox as they are now; see `QueuedTaskOps.sync`.
    @discardableResult
    private func syncQueue() async -> Bool {
        queue.sync(await outbox.tasks())
    }

    /// Put the lists on screen: what the server last said, with the queued
    /// task calls done to it. Calls the server refused are left out of that
    /// and listed for the user instead.
    private func show() {
        failed = queue.items.filter(\.failedPermanently)
        waiting = queue.items.count { !$0.failedPermanently && !queue.sent.contains($0.id) }

        // The day was changed and its plans aren't in yet: the list in view
        // stays until they are.
        guard let day = agendaDay, day == selectedDate.iso else { return }

        let ops = queue.items.filter { !$0.failedPermanently }.compactMap(\.task)
        // Open ones first; the plan's order within each group.
        let rows = agenda.daily.tasks.withPending(ops, on: day)
        tasks = rows.filter { !$0.done } + rows.filter(\.done)
        if let focusedTask, !tasks.contains(where: { $0.key == focusedTask }) {
            self.focusedTask = nil
        }
        weekPlan = agenda.weekly.tasks.withPending(ops, on: nil)
    }

    /// The moment a task call was made, which is also the published time of
    /// the journal entry a completion note makes. On another day than today
    /// it is the time of day now on the selected day, so the entry is filed
    /// under the day in view, like the completion itself.
    private func nowIso() -> String {
        let now = Date()
        return IsoTime.string(isToday ? now : selectedDate.at(timeOf: now))
    }
}
