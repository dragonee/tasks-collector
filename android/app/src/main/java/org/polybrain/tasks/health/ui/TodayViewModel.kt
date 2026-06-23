package org.polybrain.tasks.health.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import java.time.DayOfWeek
import java.time.LocalDate
import java.time.OffsetDateTime
import java.time.temporal.TemporalAdjusters
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import org.polybrain.tasks.health.data.HabitKeyword
import org.polybrain.tasks.health.data.Settings
import org.polybrain.tasks.health.data.SettingsSnapshot
import org.polybrain.tasks.health.data.TaskCompleteRequest
import org.polybrain.tasks.health.data.TaskTextRequest
import org.polybrain.tasks.health.data.TasksApi
import org.polybrain.tasks.health.data.TasksClient
import org.polybrain.tasks.health.data.TodayTask
import org.polybrain.tasks.health.data.TrackHabitRequest
import org.polybrain.tasks.health.data.TripSummary

class TodayViewModel(application: Application) : AndroidViewModel(application) {

    private val settings = Settings(application)

    private val _tasks = MutableStateFlow<List<TodayTask>>(emptyList())
    val tasks: StateFlow<List<TodayTask>> = _tasks.asStateFlow()

    /** This week's plan focus lines (Weekly thread, current week). */
    private val _weekPlan = MutableStateFlow<List<String>>(emptyList())
    val weekPlan: StateFlow<List<String>> = _weekPlan.asStateFlow()

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
        abstract val text: String

        /** Tick on an unchecked task → opens the "Add a note" dialog. */
        data class AddNote(override val text: String) : PendingComplete()

        /**
         * Tap on a checked progress task (`(K/N)` with `K >= N`) → opens
         * the completed-task dialog with Add another / Reset / Cancel.
         * Plain boolean done tasks skip this path and untick immediately.
         */
        data class CompletedAction(override val text: String) : PendingComplete()
    }

    private val _pendingComplete = MutableStateFlow<PendingComplete?>(null)
    val pendingComplete: StateFlow<PendingComplete?> = _pendingComplete.asStateFlow()

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
        viewModelScope.launch { reload() }
    }

    fun add(text: String) {
        val trimmed = text.trim()
        if (trimmed.isEmpty()) return
        viewModelScope.launch {
            mutate { api -> api.addTodayTask(TaskTextRequest(trimmed, today())) }
        }
    }

    /**
     * Pull a line from this week's plan into today's tasks. Reuses the
     * same /add path as a manually typed task — the weekly plan line stays
     * put (it's the source for the week), the text is copied onto today's
     * Daily plan. `mutate`'s reload then refreshes both lists, so the item
     * appears under today's tasks and drops out of the week-plan section
     * (which filters out lines already on today).
     */
    fun addPlanItemToToday(text: String) {
        val trimmed = text.trim()
        if (trimmed.isEmpty()) return
        viewModelScope.launch {
            mutate { api -> api.addTodayTask(TaskTextRequest(trimmed, today())) }
        }
    }

    /**
     * Copy a task onto the actual current day. Offered from a task's context
     * menu only while browsing some other day. Reuses the same /add path as a
     * typed task, but pins the date to the real today rather than the selected
     * day, so the task lands on today's Daily plan while staying put on the day
     * being viewed. `mutate`'s reload refreshes the day in view (unchanged when
     * that isn't today); navigating to today then shows the copy.
     */
    fun copyToToday(text: String) {
        val trimmed = text.trim()
        if (trimmed.isEmpty()) return
        viewModelScope.launch {
            mutate { api ->
                api.addTodayTask(TaskTextRequest(trimmed, LocalDate.now().toString()))
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
     * - `done = false` on a fully-complete *progress* task (`(K/N)`
     *   with `K >= N`) → stash a [CompletedAction] pending state; the
     *   UI opens the completed-task dialog with Add another / Reset /
     *   Cancel. No optimistic flip — the row keeps its checked look
     *   until the user picks Reset.
     * - `done = false` on a plain task → fire `/complete` immediately,
     *   no modal, no journal entry.
     */
    fun requestSetDone(text: String, done: Boolean) {
        if (done) {
            _pendingComplete.value = PendingComplete.AddNote(text)
            return
        }
        if (isCompleteProgressTask(text)) {
            _pendingComplete.value = PendingComplete.CompletedAction(text)
            return
        }
        viewModelScope.launch {
            _tasks.value = _tasks.value.map { t ->
                if (t.text == text) t.copy(done = false) else t
            }
            mutate { api ->
                api.completeTodayTask(TaskCompleteRequest(text, false, nowIso()))
            }
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
        viewModelScope.launch {
            _tasks.value = _tasks.value.map { t ->
                if (t.text == pending.text) t.copy(done = true) else t
            }
            mutate { api ->
                api.completeTodayTask(
                    TaskCompleteRequest(pending.text, true, nowIso(), note, storyId)
                )
            }
        }
    }

    /**
     * Add another button on the completed-task dialog. Sends `done=true`
     * — on the backend that advances `(K/N)` to `(K+1/N)` and keeps the
     * row checked. The optional note flows through as a journal entry
     * just like a normal tick.
     */
    fun confirmAddAnother(note: String) {
        val pending = _pendingComplete.value as? PendingComplete.CompletedAction ?: return
        _pendingComplete.value = null
        viewModelScope.launch {
            // Row stays visually checked; no optimistic change needed.
            mutate { api ->
                api.completeTodayTask(
                    TaskCompleteRequest(pending.text, true, nowIso(), note)
                )
            }
        }
    }

    /**
     * Reset button on the completed-task dialog. Sends `done=false` —
     * on the backend that returns `(K/N)` to pristine `(N)` and clears
     * `Reflection.good`. No note, no journal entry.
     */
    fun confirmReset() {
        val pending = _pendingComplete.value as? PendingComplete.CompletedAction ?: return
        _pendingComplete.value = null
        viewModelScope.launch {
            _tasks.value = _tasks.value.map { t ->
                if (t.text == pending.text) t.copy(done = false) else t
            }
            mutate { api ->
                api.completeTodayTask(
                    TaskCompleteRequest(pending.text, false, nowIso())
                )
            }
        }
    }

    /** Cancel / backdrop dismiss on either dialog. */
    fun cancelCompletion() {
        _pendingComplete.value = null
    }

    fun delete(text: String) {
        viewModelScope.launch {
            _tasks.value = _tasks.value.filterNot { it.text == text }
            mutate { api -> api.deleteTodayTask(TaskTextRequest(text, today())) }
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
            _tasks.value = api.listTodayTasks(today()).items
            _weekPlan.value = api.listPlans("Weekly", endOfWeek()).results
                .firstOrNull()
                ?.focus
                ?.lineSequence()
                ?.map { it.trim() }
                ?.filter { it.isNotEmpty() }
                ?.toList()
                ?: emptyList()
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

    // The selected day in ISO 8601 (YYYY-MM-DD). Used by /add, /delete,
    // /list — they only need to know which day the user means.
    private fun today(): String = _selectedDate.value.toString()

    // Canonical pub_date of the Weekly plan covering the selected day: the
    // Sunday ending that week. Mirrors the server's make_last_day_of_the_week
    // (utils/datetime.py), which is also what /plans/add-task/ uses for the
    // "this_week" timeframe. Keyed off the selected day so the week-plan
    // section follows the date you're browsing.
    private fun endOfWeek(): String =
        _selectedDate.value
            .with(TemporalAdjusters.nextOrSame(DayOfWeek.SUNDAY))
            .toString()

    // Full wall-clock timestamp with the device's current offset, ISO
    // 8601 (e.g. 2026-05-21T15:42:33.123+02:00). Used by /complete so the
    // server records the exact moment as the JournalAdded published time.
    // When browsing a different day, we keep the current time-of-day but
    // swap the date to the selected one, so the server's
    // pub_date = published.date() lands the Plan/Reflection write on the
    // day being viewed rather than on the real today.
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

    companion object {
        // Mirrors services/today/progress.py:PROGRESS_RE. Used only to
        // decide which dialog to open on an "untick" tap — the server
        // is still the source of truth for actual progression.
        private val PROGRESS_RE = Regex("""\((\d+)(?:/(\d+))?\)""")

        /**
         * True when [text] carries a progress marker `(K/N)` whose
         * current step is at or past its total — i.e. a state where the
         * row is rendered as checked. `(N)` pristine markers and
         * partial `(K/N)` (K<N) return false.
         */
        internal fun isCompleteProgressTask(text: String): Boolean {
            val match = PROGRESS_RE.find(text) ?: return false
            val current = match.groupValues[1].toIntOrNull() ?: return false
            val totalRaw = match.groupValues[2]
            if (totalRaw.isEmpty()) return false  // (N) form — never complete
            val total = totalRaw.toIntOrNull() ?: return false
            if (total < 1) return false
            return current >= total
        }
    }
}
