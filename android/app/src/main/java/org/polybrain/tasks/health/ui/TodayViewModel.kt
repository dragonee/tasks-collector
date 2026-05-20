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

    data class PendingComplete(val text: String)

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
     * - On uncheck (done=false) the API call fires immediately with no
     *   journal entry — the [x] marker doesn't make sense for backing
     *   out of a completion.
     * - On check (done=true) we stash the request as [pendingComplete]
     *   so the UI can show the journal-note modal; the API call doesn't
     *   fire until [confirmCompletion] or is dropped by
     *   [cancelCompletion]. No optimistic flip — the checkbox stays
     *   visually un-ticked until the user confirms.
     */
    fun requestSetDone(text: String, done: Boolean) {
        if (done) {
            _pendingComplete.value = PendingComplete(text)
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

    fun confirmCompletion(note: String) {
        val pending = _pendingComplete.value ?: return
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
}
