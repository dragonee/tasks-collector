package org.polybrain.tasks.health.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import java.time.LocalDate
import java.time.OffsetDateTime
import java.util.UUID
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import org.polybrain.tasks.health.data.HabitKeyword
import org.polybrain.tasks.health.data.PlanRef
import org.polybrain.tasks.health.data.PlanTextRequest
import org.polybrain.tasks.health.data.Settings
import org.polybrain.tasks.health.data.SettingsSnapshot
import org.polybrain.tasks.health.data.Task
import org.polybrain.tasks.health.data.TaskCompleteRequest
import org.polybrain.tasks.health.data.TaskMoveRequest
import org.polybrain.tasks.health.data.TasksApi
import org.polybrain.tasks.health.data.TasksClient
import org.polybrain.tasks.health.data.TrackHabitRequest
import org.polybrain.tasks.health.data.TripSummary

class TodayViewModel(application: Application) : AndroidViewModel(application) {

    private val settings = Settings(application)

    /** The selected day's tasks, open ones first. */
    private val _tasks = MutableStateFlow<List<Task>>(emptyList())
    val tasks: StateFlow<List<Task>> = _tasks.asStateFlow()

    /**
     * The tasks of the week the selected day is in (Weekly thread). Each
     * knows whether it is done, wherever that was ticked.
     */
    private val _weekPlan = MutableStateFlow<List<Task>>(emptyList())
    val weekPlan: StateFlow<List<Task>> = _weekPlan.asStateFlow()

    private val _loading = MutableStateFlow(false)
    val loading: StateFlow<Boolean> = _loading.asStateFlow()

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
        viewModelScope.launch {
            mutate { api -> api.planText(PlanTextRequest(trimmed, today())) }
        }
    }

    /**
     * Pull a task of this week's plan into the selected day. It is the same
     * task on both plans, so ticking it on the day ticks it for the week.
     * `mutate`'s reload then moves it from the week-plan section (which
     * leaves out what is on the day already) to the day's list.
     */
    fun addPlanItemToToday(task: Task) {
        viewModelScope.launch {
            mutate { api -> planOn(api, task, today()) }
        }
    }

    /**
     * Put a task on the actual current day as well. Offered from a task's
     * context menu only while browsing some other day. `mutate`'s reload
     * refreshes the day in view (unchanged when that isn't today);
     * navigating to today then shows it.
     */
    fun copyToToday(task: Task) {
        viewModelScope.launch {
            mutate { api -> planOn(api, task, LocalDate.now().toString()) }
        }
    }

    /**
     * Move a task to tomorrow's plan. It is the same task there, steps done
     * so far included. Offered from a task's context menu only while viewing
     * today. `mutate`'s reload reflects the result — the row leaves today and
     * reappears when you step to tomorrow.
     */
    fun moveToTomorrow(task: Task) {
        viewModelScope.launch {
            mutate { api ->
                api.moveTask(
                    idOf(api, task),
                    TaskMoveRequest(today(), LocalDate.now().plusDays(1).toString()),
                )
            }
        }
    }

    /**
     * Entry point for the checkbox tap.
     *
     * Branching:
     * - `done = true` (ticking an unchecked row) → stash an [AddNote]
     *   pending state; the UI opens the add-note dialog and the API
     *   call doesn't fire until [confirmCompletion]. No optimistic flip.
     * - `done = false` on a counted task with all its steps done → stash a
     *   [CompletedAction] pending state; the UI opens the completed-task
     *   dialog with Add another / Reset / Cancel. No optimistic flip — the
     *   row keeps its checked look until the user picks Reset.
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
        viewModelScope.launch {
            showDone(task, false)
            mutate { api -> api.reopenTask(idOf(api, task)) }
        }
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
        val request = completeRequest(note, storyId)
        viewModelScope.launch {
            // A counted task with steps left stays open after this one; the
            // reload shows where it stands.
            if (pending.task.doneCount + 1 >= pending.task.total) {
                showDone(pending.task, true)
            }
            mutate { api -> api.completeTask(idOf(api, pending.task), request) }
        }
    }

    /**
     * Add another button on the completed-task dialog: one more step of a
     * counted task that has all of them. The row stays checked. The optional
     * note flows through as a journal entry just like a normal tick.
     */
    fun confirmAddAnother(note: String) {
        val pending = _pendingComplete.value as? PendingComplete.CompletedAction ?: return
        _pendingComplete.value = null
        val request = completeRequest(note, storyId = null)
        viewModelScope.launch {
            // Row stays visually checked; no optimistic change needed.
            mutate { api -> api.completeTask(idOf(api, pending.task), request) }
        }
    }

    /**
     * Reset button on the completed-task dialog: takes back the last step
     * done, and its line in the reflection. No note, no journal entry.
     */
    fun confirmReset() {
        val pending = _pendingComplete.value as? PendingComplete.CompletedAction ?: return
        _pendingComplete.value = null
        viewModelScope.launch {
            showDone(pending.task, false)
            mutate { api -> api.reopenTask(idOf(api, pending.task)) }
        }
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
        viewModelScope.launch {
            _tasks.value = _tasks.value.filterNot { it.key == task.key }
            mutate { api -> api.unplanTask(idOf(api, task), PlanRef(today())) }
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
            _tasks.value = emptyList()
            _weekPlan.value = emptyList()
            _activeTrip.value = null
            return
        }
        _loading.value = true
        try {
            val api = buildApi(snapshot)
            val agenda = api.agenda(today())
            // Open ones first; the plan's order within each group (sortedBy
            // is stable).
            _tasks.value = agenda.daily.tasks.sortedBy { it.done }
            // Drop focus if its task is gone, otherwise the "exit focus mode"
            // item would vanish with the row.
            if (_focusedTask.value != null && _tasks.value.none { it.key == _focusedTask.value }) {
                _focusedTask.value = null
            }
            _weekPlan.value = agenda.weekly.tasks
            _activeTrip.value = api.listTrips(page = 1, pageSize = 1).active.firstOrNull()
            _error.value = null
        } catch (t: Throwable) {
            _error.value = t.message ?: t.javaClass.simpleName
        } finally {
            _loading.value = false
        }
    }

    private suspend fun mutate(block: suspend (TasksApi) -> Unit) {
        val snapshot = settings.snapshot()
        _configured.value = snapshot.isConfigured
        if (!snapshot.isConfigured) {
            _error.value = "Configure server URL and API token first."
            return
        }
        try {
            block(buildApi(snapshot))
            reload()
        } catch (t: Throwable) {
            _error.value = t.message ?: t.javaClass.simpleName
            reload()
        }
    }

    private fun buildApi(snapshot: SettingsSnapshot): TasksApi =
        TasksClient.build(snapshot.serverUrl, snapshot.apiToken)

    /** Show [task] as done or not before the server answers. */
    private fun showDone(task: Task, done: Boolean) {
        _tasks.value = _tasks.value.map { t ->
            if (t.key == task.key) t.copy(done = done) else t
        }
    }

    /**
     * The id of [task]. A plain line of a plan has none until something is
     * done with it: planning its text where it already is makes it a task.
     */
    private suspend fun idOf(api: TasksApi, task: Task): String =
        task.id ?: checkNotNull(api.planText(PlanTextRequest(task.text, today())).id)

    /** Put [task] on the Daily plan of [date] as well. */
    private suspend fun planOn(api: TasksApi, task: Task, date: String) {
        val id = task.id
        if (id == null) {
            // A plain line (of the week's plan, say): the server finds it by
            // its text and makes it a task on both plans.
            api.planText(PlanTextRequest(task.text, date))
        } else {
            api.planTask(id, PlanRef(date))
        }
    }

    private fun completeRequest(note: String, storyId: Long?) = TaskCompleteRequest(
        day = today(),
        at = nowIso(),
        note = note,
        storyId = storyId,
        idempotencyKey = UUID.randomUUID().toString(),
    )

    // The selected day in ISO 8601 (YYYY-MM-DD): the day every call here is
    // about.
    private fun today(): String = _selectedDate.value.toString()

    // Full wall-clock timestamp with the device's current offset, ISO
    // 8601 (e.g. 2026-05-21T15:42:33.123+02:00): the published time of the
    // journal entry a completion note makes. When browsing a different day,
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
