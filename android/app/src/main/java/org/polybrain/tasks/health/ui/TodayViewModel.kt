package org.polybrain.tasks.health.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import androidx.work.WorkManager
import java.time.LocalDate
import java.time.OffsetDateTime
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import org.polybrain.tasks.health.data.AgendaResponse
import org.polybrain.tasks.health.data.HabitKeyword
import org.polybrain.tasks.health.data.Outbox
import org.polybrain.tasks.health.data.OutboxItem
import org.polybrain.tasks.health.data.QueuedTaskOps
import org.polybrain.tasks.health.data.SavedPlans
import org.polybrain.tasks.health.data.Settings
import org.polybrain.tasks.health.data.SettingsSnapshot
import org.polybrain.tasks.health.data.Task
import org.polybrain.tasks.health.data.TaskOp
import org.polybrain.tasks.health.data.TasksApi
import org.polybrain.tasks.health.data.TasksClient
import org.polybrain.tasks.health.data.TrackHabitRequest
import org.polybrain.tasks.health.data.TripSummary
import org.polybrain.tasks.health.data.withPending
import org.polybrain.tasks.health.sync.SyncScheduler

/**
 * The Today list. What is done to a task here is not sent from here: it is
 * queued in the [Outbox] (see [queueOp]) and delivered by the outbox worker,
 * now or when there is a connection again. The lists show what the server
 * last said with what is queued on top ([show]), so a tick shows at once and
 * stays through an offline spell. What the server said is kept on the phone
 * ([SavedPlans]): opened without a connection, the list is the day's plans
 * as last fetched.
 */
class TodayViewModel(application: Application) : AndroidViewModel(application) {

    private val settings = Settings(application)
    private val outbox = Outbox(application)
    private val savedPlans = SavedPlans(application)
    private val workManager = WorkManager.getInstance(application)

    /** The plans of [agendaDay] as the server last gave them. */
    private var agenda = AgendaResponse()
    private var agendaDay: String? = null

    /** The task calls shown on top of [agenda]. */
    private val queue = QueuedTaskOps()

    /** Counts fetches of the plans, so that only the latest one's answer is used. */
    private var reloads = 0

    /** Task calls are queued one at a time, in the order they were made. */
    private val queueing = Mutex()

    /** The selected day's tasks, open ones first, with what is queued for them. */
    private val _tasks = MutableStateFlow<List<Task>>(emptyList())
    val tasks: StateFlow<List<Task>> = _tasks.asStateFlow()

    /**
     * The tasks of the week the selected day is in (Weekly thread). Each
     * knows whether it is done, wherever that was ticked.
     */
    private val _weekPlan = MutableStateFlow<List<Task>>(emptyList())
    val weekPlan: StateFlow<List<Task>> = _weekPlan.asStateFlow()

    /** How many task calls are waiting to be sent. */
    private val _waiting = MutableStateFlow(0)
    val waiting: StateFlow<Int> = _waiting.asStateFlow()

    /**
     * Task calls the server refused. They are not shown as done, and stay
     * queued until the user sends them again or throws them away.
     */
    private val _failed = MutableStateFlow<List<OutboxItem>>(emptyList())
    val failed: StateFlow<List<OutboxItem>> = _failed.asStateFlow()

    private val _loading = MutableStateFlow(false)
    val loading: StateFlow<Boolean> = _loading.asStateFlow()

    /**
     * When the plans on screen were fetched, if they are the ones kept on
     * the phone (the server couldn't be asked); null when they are fresh.
     */
    private val _savedAt = MutableStateFlow<Long?>(null)
    val savedAt: StateFlow<Long?> = _savedAt.asStateFlow()

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    private val _configured = MutableStateFlow(false)
    val configured: StateFlow<Boolean> = _configured.asStateFlow()

    /**
     * Which day the Today view is showing. Defaults to the device's current
     * day; the prev/next chevrons move it backward/forward. Every endpoint
     * the screen talks to (list / add / complete / delete and the weekly
     * plan lookup) is keyed off this date, so past days are browsable and
     * future days are pre-fillable — no day is special-cased.
     */
    private val _selectedDate = MutableStateFlow(LocalDate.now())
    val selectedDate: StateFlow<LocalDate> = _selectedDate.asStateFlow()

    /**
     * What the user just initiated by tapping a row's checkbox. Drives
     * which dialog (if any) is shown. ``null`` = no pending interaction.
     */
    sealed class PendingComplete {
        abstract val task: Task

        /** Tick on an unchecked task → opens the "Add a note" dialog. */
        data class AddNote(override val task: Task) : PendingComplete()

        /**
         * Tap on a checked counted task (all its steps done) → opens the
         * completed-task dialog with Add another / Reset / Cancel. Plain
         * done tasks skip this path and untick immediately.
         */
        data class CompletedAction(override val task: Task) : PendingComplete()
    }

    private val _pendingComplete = MutableStateFlow<PendingComplete?>(null)
    val pendingComplete: StateFlow<PendingComplete?> = _pendingComplete.asStateFlow()

    /**
     * Key ([Task.key]) of the task the user is currently focusing on, or null
     * when focus mode is off. In focus mode the screen hides everything except this task
     * and already-finished ones, so only the one thing left to do is in view.
     * Cleared on day change and when the focused task disappears from a reload
     * (so its "exit focus" menu item can never become unreachable).
     */
    private val _focusedTask = MutableStateFlow<String?>(null)
    val focusedTask: StateFlow<String?> = _focusedTask.asStateFlow()

    /**
     * The most recently started active trip, refreshed alongside the task
     * list. Drives the "Save to trip" button on the add-note dialog; null
     * when no trip is active.
     */
    private val _activeTrip = MutableStateFlow<TripSummary?>(null)
    val activeTrip: StateFlow<TripSummary?> = _activeTrip.asStateFlow()

    /**
     * Available habit keywords for the "track a habit" dialog, fetched once
     * and cached for the ViewModel's lifetime — the user's keyword set rarely
     * changes. Empty until [loadHabitKeywords] first succeeds.
     */
    private val _habitKeywords = MutableStateFlow<List<HabitKeyword>>(emptyList())
    val habitKeywords: StateFlow<List<HabitKeyword>> = _habitKeywords.asStateFlow()

    /** Whether the track-a-habit dialog is open. */
    private val _habitDialogOpen = MutableStateFlow(false)
    val habitDialogOpen: StateFlow<Boolean> = _habitDialogOpen.asStateFlow()

    /** True while the keyword list is being fetched (drives the dialog spinner). */
    private val _habitKeywordsLoading = MutableStateFlow(false)
    val habitKeywordsLoading: StateFlow<Boolean> = _habitKeywordsLoading.asStateFlow()

    /** True while a habit is being posted; gates the dialog's Track button. */
    private val _habitSaving = MutableStateFlow(false)
    val habitSaving: StateFlow<Boolean> = _habitSaving.asStateFlow()

    /** Last habit-dialog error (load or post), shown inline; null = none. */
    private val _habitError = MutableStateFlow<String?>(null)
    val habitError: StateFlow<String?> = _habitError.asStateFlow()

    init {
        // Whenever the outbox worker gets somewhere: see what is left of the
        // queue, and fetch the plans again once calls have been sent.
        viewModelScope.launch {
            workManager.getWorkInfosForUniqueWorkFlow(SyncScheduler.OUTBOX).collect {
                if (syncQueue()) refresh() else show()
            }
        }
    }

    fun refresh() {
        viewModelScope.launch { reload() }
    }

    /** Chevron-left: step the view back one day and reload. */
    fun previousDay() = goToDate(_selectedDate.value.minusDays(1))

    /** Chevron-right: step the view forward one day and reload. */
    fun nextDay() = goToDate(_selectedDate.value.plusDays(1))

    /** Tap on the date label: jump straight back to the current day. */
    fun goToToday() = goToDate(LocalDate.now())

    private fun goToDate(date: LocalDate) {
        if (date == _selectedDate.value) return
        _selectedDate.value = date
        // Any pending dialog refers to a task on the previous day's list.
        _pendingComplete.value = null
        // Focus is scoped to the day it was started on.
        _focusedTask.value = null
        viewModelScope.launch { reload() }
    }

    /**
     * Context-menu toggle: focus this task (entering focus mode), or exit focus
     * mode if this task is already the focused one. Pure view state — nothing is
     * sent to the server.
     */
    fun toggleFocus(task: Task) {
        _focusedTask.value = if (_focusedTask.value == task.key) null else task.key
    }

    /** A task typed in: planned for the selected day. Not written to the board. */
    fun add(text: String) {
        val trimmed = text.trim()
        if (trimmed.isEmpty()) return
        queueOp(TaskOp.Type.PLAN, Task(text = trimmed))
    }

    /**
     * Pull a task of this week's plan into the selected day. It is the same
     * task on both plans, so ticking it on the day ticks it for the week.
     * It moves from the week-plan section (which leaves out what is on the
     * day already) to the day's list. A plain line of the week's plan has no
     * id: the server finds it by its text and makes it a task on both plans.
     */
    fun addPlanItemToToday(task: Task) {
        queueOp(TaskOp.Type.PLAN, task)
    }

    /**
     * Put a task on the actual current day as well. Offered from a task's
     * context menu only while browsing some other day. The day in view
     * stays as it is; navigating to today then shows it.
     */
    fun copyToToday(task: Task) {
        queueOp(TaskOp.Type.PLAN, task, date = LocalDate.now().toString())
    }

    /**
     * Move a task to tomorrow's plan. It is the same task there, steps done
     * so far included. Offered from a task's context menu only while viewing
     * today. The row leaves today and reappears when you step to tomorrow.
     */
    fun moveToTomorrow(task: Task) {
        queueOp(
            TaskOp.Type.MOVE,
            task,
            toDate = LocalDate.now().plusDays(1).toString(),
        )
    }

    /**
     * Entry point for the checkbox tap.
     *
     * Branching:
     * - `done = true` (ticking an unchecked row) → stash an [AddNote]
     *   pending state; the UI opens the add-note dialog and nothing is
     *   queued until [confirmCompletion]. The row stays unchecked till then.
     * - `done = false` on a counted task with all its steps done → stash a
     *   [CompletedAction] pending state; the UI opens the completed-task
     *   dialog with Add another / Reset / Cancel. The row keeps its checked
     *   look until the user picks Reset.
     * - `done = false` on a plain task → take it back immediately, no modal.
     */
    fun requestSetDone(task: Task, done: Boolean) {
        if (done) {
            _pendingComplete.value = PendingComplete.AddNote(task)
            return
        }
        if (task.isCountedAndDone) {
            _pendingComplete.value = PendingComplete.CompletedAction(task)
            return
        }
        queueOp(TaskOp.Type.REOPEN, task)
    }

    /** Save button on the add-note dialog. */
    fun confirmCompletion(note: String) {
        completePending(note, storyId = null)
    }

    /**
     * Save-to-trip button on the add-note dialog: same completion, but the
     * journal entry is linked to the active trip. Falls back to a plain
     * save if the trip vanished since the dialog opened.
     */
    fun confirmCompletionToTrip(note: String) {
        completePending(note, storyId = _activeTrip.value?.id)
    }

    private fun completePending(note: String, storyId: Long?) {
        val pending = _pendingComplete.value as? PendingComplete.AddNote ?: return
        _pendingComplete.value = null
        // Crossing off the focused task ends focus mode — its one job is done,
        // so fall back to the full list (the completed task included).
        if (_focusedTask.value == pending.task.key) _focusedTask.value = null
        queueOp(TaskOp.Type.COMPLETE, pending.task, note = note, storyId = storyId)
    }

    /**
     * Add another button on the completed-task dialog: one more step of a
     * counted task that has all of them. The row stays checked. The optional
     * note flows through as a journal entry just like a normal tick.
     */
    fun confirmAddAnother(note: String) {
        val pending = _pendingComplete.value as? PendingComplete.CompletedAction ?: return
        _pendingComplete.value = null
        queueOp(TaskOp.Type.COMPLETE, pending.task, note = note)
    }

    /**
     * Reset button on the completed-task dialog: takes back the last step
     * done, and its line in the reflection. No note, no journal entry.
     */
    fun confirmReset() {
        val pending = _pendingComplete.value as? PendingComplete.CompletedAction ?: return
        _pendingComplete.value = null
        queueOp(TaskOp.Type.REOPEN, pending.task)
    }

    /** Cancel / backdrop dismiss on either dialog. */
    fun cancelCompletion() {
        _pendingComplete.value = null
    }

    /**
     * Take the task off the selected day's plan. The board is left alone, and
     * a task that was done stays done.
     */
    fun delete(task: Task) {
        queueOp(TaskOp.Type.UNPLAN, task)
    }

    /** Send a task call the server refused once more. */
    fun retrySync(item: OutboxItem) {
        viewModelScope.launch {
            withContext(Dispatchers.IO) {
                outbox.update(item.copy(failedPermanently = false, lastError = null))
            }
            syncQueue()
            show()
            SyncScheduler.drainOutbox(getApplication())
        }
    }

    /** Throw a task call away without sending it. */
    fun discardSync(item: OutboxItem) {
        viewModelScope.launch {
            withContext(Dispatchers.IO) { outbox.remove(item) }
            queue.discard(item.id)
            show()
        }
    }

    fun clearError() {
        _error.value = null
    }

    /**
     * Open the track-a-habit dialog and make sure the keyword list is loaded.
     * The list is cached across opens, so this only hits the network the first
     * time (or after a previous failure left it empty).
     */
    fun openHabitDialog() {
        _habitError.value = null
        _habitDialogOpen.value = true
        if (_habitKeywords.value.isEmpty()) loadHabitKeywords()
    }

    fun closeHabitDialog() {
        if (_habitSaving.value) return
        _habitDialogOpen.value = false
    }

    /**
     * Fetch the user's available habit keywords. No-op while a fetch is already
     * in flight or, unless [force] is set, when the cache is already populated.
     */
    fun loadHabitKeywords(force: Boolean = false) {
        if (_habitKeywordsLoading.value) return
        if (!force && _habitKeywords.value.isNotEmpty()) return
        viewModelScope.launch {
            val snapshot = settings.snapshot()
            if (!snapshot.isConfigured) {
                _habitError.value = "Configure server URL and API token first."
                return@launch
            }
            _habitKeywordsLoading.value = true
            try {
                _habitKeywords.value = buildApi(snapshot).listHabitKeywords(today())
                _habitError.value = null
            } catch (t: Throwable) {
                _habitError.value = t.message ?: t.javaClass.simpleName
            } finally {
                _habitKeywordsLoading.value = false
            }
        }
    }

    /**
     * Record a habit for the selected day via the idempotent keyword endpoint
     * (upsert on habit+date). Closes the dialog on success. The keyword cache
     * is left intact — re-tracking just updates that day's note server-side.
     */
    fun trackHabit(keyword: String, note: String) {
        if (_habitSaving.value) return
        viewModelScope.launch {
            val snapshot = settings.snapshot()
            if (!snapshot.isConfigured) {
                _habitError.value = "Configure server URL and API token first."
                return@launch
            }
            _habitSaving.value = true
            _habitError.value = null
            try {
                buildApi(snapshot).trackHabit(
                    TrackHabitRequest(keyword = keyword, date = today(), note = note.trim())
                )
                _habitDialogOpen.value = false
            } catch (t: Throwable) {
                _habitError.value = t.message ?: t.javaClass.simpleName
            } finally {
                _habitSaving.value = false
            }
        }
    }

    private suspend fun reload() {
        val snapshot = settings.snapshot()
        _configured.value = snapshot.isConfigured
        if (!snapshot.isConfigured) {
            agenda = AgendaResponse()
            agendaDay = null
            _savedAt.value = null
            _tasks.value = emptyList()
            _weekPlan.value = emptyList()
            _activeTrip.value = null
            return
        }
        val account = SavedPlans.account(snapshot.serverUrl, snapshot.apiToken)
        val generation = ++reloads
        val day = today()
        syncQueue()
        // The calls sent before the plans are asked for are in the answer.
        val covered = queue.sent
        _loading.value = true
        try {
            val api = buildApi(snapshot)
            val fetched = api.agenda(day)
            // Not kept (a full disk) is no reason not to show them.
            withContext(Dispatchers.IO) { runCatching { savedPlans.save(account, day, fetched) } }
            val trip = api.listTrips(page = 1, pageSize = 1).active.firstOrNull()
            // A later fetch is on its way: its answer is the one to show.
            if (generation != reloads) return
            agenda = fetched
            agendaDay = day
            _savedAt.value = null
            queue.fetched(covered)
            _activeTrip.value = trip
            _error.value = null
        } catch (t: Throwable) {
            if (generation != reloads) return
            _error.value = t.message ?: t.javaClass.simpleName
            if (agendaDay != day) {
                // Nothing of this day in hand (no connection): the plans kept
                // from the last fetch, or else an empty list, with what is
                // queued on top.
                val saved = withContext(Dispatchers.IO) { savedPlans.load(account, day) }
                if (generation != reloads) return
                agenda = saved?.agenda ?: AgendaResponse()
                agendaDay = day
                _savedAt.value = saved?.savedAt
            }
        } finally {
            if (generation == reloads) _loading.value = false
        }
        // Calls sent while the plans were on their way are not in them.
        if (syncQueue()) refresh()
        show()
    }

    /**
     * Queue something done to [task] and show it done. [date] is the day of
     * the plan it is about: the selected day unless said otherwise.
     */
    private fun queueOp(
        type: TaskOp.Type,
        task: Task,
        date: String = today(),
        toDate: String? = null,
        note: String? = null,
        storyId: Long? = null,
    ) {
        val op = TaskOp(type, task, date, toDate = toDate, note = note, storyId = storyId)
        // The moment of the tap, not of the delivery.
        val published = nowIso()
        viewModelScope.launch {
            queueing.withLock {
                val snapshot = settings.snapshot()
                _configured.value = snapshot.isConfigured
                if (!snapshot.isConfigured) {
                    _error.value = "Configure server URL and API token first."
                    return@launch
                }
                withContext(Dispatchers.IO) { outbox.enqueueTask(op, published) }
                syncQueue()
                show()
            }
            SyncScheduler.drainOutbox(getApplication())
        }
    }

    /** Take the task calls of the outbox as they are now; see [QueuedTaskOps.sync]. */
    private suspend fun syncQueue(): Boolean =
        queue.sync(withContext(Dispatchers.IO) { outbox.tasks() })

    /**
     * Put the lists on screen: what the server last said, with the queued
     * task calls done to it. Calls the server refused are left out of that
     * and listed for the user instead.
     */
    private fun show() {
        _failed.value = queue.items.filter { it.failedPermanently }
        _waiting.value = queue.items.count { !it.failedPermanently && it.id !in queue.sent }

        // The day was changed and its plans aren't in yet: the list in view
        // stays until they are.
        val day = agendaDay ?: return
        if (day != today()) return

        val ops = queue.items.filterNot { it.failedPermanently }.mapNotNull { it.task }
        // Open ones first; the plan's order within each group (sortedBy is
        // stable).
        _tasks.value = agenda.daily.tasks.withPending(ops, day).sortedBy { it.done }
        // Drop focus if its task is gone, otherwise the "exit focus mode"
        // item would vanish with the row.
        if (_focusedTask.value != null && _tasks.value.none { it.key == _focusedTask.value }) {
            _focusedTask.value = null
        }
        _weekPlan.value = agenda.weekly.tasks.withPending(ops, null)
    }

    private fun buildApi(snapshot: SettingsSnapshot): TasksApi =
        TasksClient.build(snapshot.serverUrl, snapshot.apiToken)

    // The selected day in ISO 8601 (YYYY-MM-DD): the day every call here is
    // about.
    private fun today(): String = _selectedDate.value.toString()

    // Full wall-clock timestamp with the device's current offset, ISO
    // 8601 (e.g. 2026-05-21T15:42:33.123+02:00): the moment a task call was
    // made, and the published time of the journal entry a completion note
    // makes. When browsing a different day,
    // we keep the current time-of-day but swap the date to the selected one,
    // so the entry is filed under the day being viewed, like the completion
    // itself.
    private fun nowIso(): String {
        val now = OffsetDateTime.now()
        val selected = _selectedDate.value
        if (selected == now.toLocalDate()) return now.toString()
        return now
            .withYear(selected.year)
            .withMonth(selected.monthValue)
            .withDayOfMonth(selected.dayOfMonth)
            .toString()
    }
}
