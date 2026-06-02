package org.polybrain.tasks.health.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import org.polybrain.tasks.health.data.BoardItem
import org.polybrain.tasks.health.data.Settings
import org.polybrain.tasks.health.data.SettingsSnapshot
import org.polybrain.tasks.health.data.TaskTextRequest
import org.polybrain.tasks.health.data.TasksApi
import org.polybrain.tasks.health.data.TasksClient

/**
 * Backs the "add from board" picker: loads the flattened board, tracks the
 * MoSCoW filter and the multi-selection, and copies the selected items onto
 * a given day's Today list by reusing the existing /task/add/ endpoint.
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

    /** Texts of the currently-selected items. Keyed by text to match the rest
     * of the system (TodayTask, board lookups by text). */
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

    fun toggleSelection(text: String) {
        _selected.value = _selected.value.toMutableSet().apply {
            if (!add(text)) remove(text)
        }
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
     * Add every selected item to [date]'s Today list, then invoke [onDone].
     *
     * Items are sent sequentially in board order via the existing /task/add/
     * endpoint (idempotent on the server via add_unique_line, so a retry that
     * re-adds an already-present line is harmless). On full success we call
     * [onDone] so the caller can pop back to Today; on partial failure we
     * surface an error and keep the failed items selected for retry.
     */
    fun addSelected(date: String, onDone: () -> Unit) {
        val texts = _selected.value
        if (texts.isEmpty()) return
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
            for (item in _items.value.filter { it.text in texts }) {
                try {
                    api.addTodayTask(TaskTextRequest(item.text, date))
                } catch (t: Throwable) {
                    failures.add(item.text)
                }
            }
            if (failures.isEmpty()) {
                onDone()
            } else {
                _error.value = "Failed to add ${failures.size} of ${texts.size} item(s)."
                _selected.value = failures.toSet()
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
