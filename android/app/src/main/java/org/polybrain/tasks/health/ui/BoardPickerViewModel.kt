package org.polybrain.tasks.health.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import org.polybrain.tasks.health.data.BoardItem
import org.polybrain.tasks.health.data.PlanItemRequest
import org.polybrain.tasks.health.data.Settings
import org.polybrain.tasks.health.data.SettingsSnapshot
import org.polybrain.tasks.health.data.TasksApi
import org.polybrain.tasks.health.data.TasksClient
import org.polybrain.tasks.health.data.UnscheduledTaskRequest

/**
 * Backs the "add from board" picker: loads the flattened board, tracks the
 * MoSCoW filter and the multi-selection, and plans the selected items for a
 * given day: each becomes a task (or is the task it already has).
 *
 * Mirrors [TodayViewModel]'s settings / buildApi / reload / error handling.
 */
class BoardPickerViewModel(application: Application) : AndroidViewModel(application) {

    private val settings = Settings(application)

    private val _items = MutableStateFlow<List<BoardItem>>(emptyList())
    val items: StateFlow<List<BoardItem>> = _items.asStateFlow()

    private val _loading = MutableStateFlow(false)
    val loading: StateFlow<Boolean> = _loading.asStateFlow()

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    private val _configured = MutableStateFlow(false)
    val configured: StateFlow<Boolean> = _configured.asStateFlow()

    /** Ids of the currently-selected items. */
    private val _selected = MutableStateFlow<Set<String>>(emptySet())
    val selected: StateFlow<Set<String>> = _selected.asStateFlow()

    /** Active MoSCoW filter chips (bucket ids, or [FILTER_NONE]). Empty set
     * means "no filter" — show everything. */
    private val _moscowFilter = MutableStateFlow<Set<String>>(emptySet())
    val moscowFilter: StateFlow<Set<String>> = _moscowFilter.asStateFlow()

    fun refresh() {
        viewModelScope.launch { reload() }
    }

    private suspend fun reload() {
        val snapshot = settings.snapshot()
        _configured.value = snapshot.isConfigured
        if (!snapshot.isConfigured) {
            _items.value = emptyList()
            return
        }
        _loading.value = true
        try {
            _items.value = buildApi(snapshot).listBoardItems().items
            _error.value = null
        } catch (t: Throwable) {
            _error.value = t.message ?: t.javaClass.simpleName
        } finally {
            _loading.value = false
        }
    }

    fun toggleSelection(itemId: String) {
        _selected.value = _selected.value.toMutableSet().apply {
            if (!add(itemId)) remove(itemId)
        }
    }

    /** Drop the whole multi-selection — used on cancel and on each fresh open
     * so a new picker session never inherits the previous one's checks. */
    fun clearSelection() {
        _selected.value = emptySet()
    }

    fun toggleFilter(id: String) {
        _moscowFilter.value = _moscowFilter.value.toMutableSet().apply {
            if (!add(id)) remove(id)
        }
    }

    fun clearError() {
        _error.value = null
    }

    /**
     * Plan every selected item for [date], then invoke [onDone].
     *
     * Items are sent one after the other in board order, each named by its
     * board and its id. Planning an item that is on the day already changes
     * nothing, so a retry is harmless. On full success we call [onDone] so
     * the caller can pop back to Today; on partial failure we surface an
     * error and keep the failed items selected for retry.
     */
    fun addSelected(date: String, onDone: () -> Unit) {
        val ids = _selected.value
        if (ids.isEmpty()) return
        viewModelScope.launch {
            val snapshot = settings.snapshot()
            _configured.value = snapshot.isConfigured
            if (!snapshot.isConfigured) {
                _error.value = "Configure server URL and API token first."
                return@launch
            }
            val api = buildApi(snapshot)
            val failures = mutableListOf<String>()
            // Preserve board order so the lines land deterministically.
            for (item in _items.value) {
                val id = item.id ?: continue
                if (id !in ids) continue
                try {
                    api.planItem(PlanItemRequest(item.boardId, id, date))
                } catch (t: Throwable) {
                    failures.add(id)
                }
            }
            if (failures.isEmpty()) {
                _selected.value = emptySet()
                onDone()
            } else {
                _error.value = "Failed to add ${failures.size} of ${ids.size} item(s)."
                _selected.value = failures.toSet()
            }
        }
    }

    /**
     * Append a free-typed unscheduled task to the board the picker is showing, via the
     * shared /boards/append/ endpoint. Unlike [addSelected] (which schedules
     * existing board items onto a given day's Plan), this only adds the line to
     * the board's backlog — for capturing something to tackle later rather than
     * pinning it to a day. The server resolves which board from the user's
     * profile, so no thread or date is sent. On success the board list is
     * reloaded so the new line appears; failures surface via [error].
     */
    fun addUnscheduledTask(text: String) {
        val trimmed = text.trim()
        if (trimmed.isEmpty()) return
        viewModelScope.launch {
            val snapshot = settings.snapshot()
            _configured.value = snapshot.isConfigured
            if (!snapshot.isConfigured) {
                _error.value = "Configure server URL and API token first."
                return@launch
            }
            try {
                buildApi(snapshot).appendUnscheduledTask(UnscheduledTaskRequest(trimmed))
                _error.value = null
                reload()
            } catch (t: Throwable) {
                _error.value = t.message ?: t.javaClass.simpleName
            }
        }
    }

    private fun buildApi(snapshot: SettingsSnapshot): TasksApi =
        TasksClient.build(snapshot.serverUrl, snapshot.apiToken)

    companion object {
        /** Sentinel filter id for items with no MoSCoW classification. */
        const val FILTER_NONE = "none"

        /**
         * Keep only items matching [filter]. Empty filter = pass everything.
         * An item's bucket is its `moscow` id, or [FILTER_NONE] when null.
         */
        fun applyFilter(items: List<BoardItem>, filter: Set<String>): List<BoardItem> {
            if (filter.isEmpty()) return items
            return items.filter { (it.moscow ?: FILTER_NONE) in filter }
        }
    }
}
