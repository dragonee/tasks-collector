package org.polybrain.tasks.health.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import java.time.LocalDate
import java.time.OffsetDateTime
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import org.polybrain.tasks.health.data.Settings
import org.polybrain.tasks.health.data.SettingsSnapshot
import org.polybrain.tasks.health.data.TaskCompleteRequest
import org.polybrain.tasks.health.data.TaskTextRequest
import org.polybrain.tasks.health.data.TasksApi
import org.polybrain.tasks.health.data.TasksClient
import org.polybrain.tasks.health.data.TodayTask

class TodayViewModel(application: Application) : AndroidViewModel(application) {

    private val settings = Settings(application)

    private val _tasks = MutableStateFlow<List<TodayTask>>(emptyList())
    val tasks: StateFlow<List<TodayTask>> = _tasks.asStateFlow()

    private val _loading = MutableStateFlow(false)
    val loading: StateFlow<Boolean> = _loading.asStateFlow()

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    private val _configured = MutableStateFlow(false)
    val configured: StateFlow<Boolean> = _configured.asStateFlow()

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

    fun refresh() {
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

    /** OK button on the add-note dialog. */
    fun confirmCompletion(note: String) {
        val pending = _pendingComplete.value as? PendingComplete.AddNote ?: return
        _pendingComplete.value = null
        viewModelScope.launch {
            _tasks.value = _tasks.value.map { t ->
                if (t.text == pending.text) t.copy(done = true) else t
            }
            mutate { api ->
                api.completeTodayTask(
                    TaskCompleteRequest(pending.text, true, nowIso(), note)
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

    private suspend fun reload() {
        val snapshot = settings.snapshot()
        _configured.value = snapshot.isConfigured
        if (!snapshot.isConfigured) {
            _tasks.value = emptyList()
            return
        }
        _loading.value = true
        try {
            val api = buildApi(snapshot)
            _tasks.value = api.listTodayTasks(today()).items
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

    // Local date in the device's current timezone, ISO 8601 (YYYY-MM-DD).
    // Used by /add, /delete, /list — they only need to know which day
    // the user means.
    private fun today(): String = LocalDate.now().toString()

    // Full wall-clock timestamp with the device's current offset, ISO
    // 8601 (e.g. 2026-05-21T15:42:33.123+02:00). Used by /complete so
    // the server can record the exact moment as the JournalAdded
    // published time, not a synthesized noon.
    private fun nowIso(): String = OffsetDateTime.now().toString()

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
