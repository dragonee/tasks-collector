package org.polybrain.tasks.health.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
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

    fun refresh() {
        viewModelScope.launch { reload() }
    }

    fun add(text: String) {
        val trimmed = text.trim()
        if (trimmed.isEmpty()) return
        viewModelScope.launch {
            mutate { api -> api.addTodayTask(TaskTextRequest(trimmed)) }
        }
    }

    fun setDone(text: String, done: Boolean) {
        viewModelScope.launch {
            // Optimistic flip — fall back to server truth on refresh.
            _tasks.value = _tasks.value.map { t ->
                if (t.text == text) t.copy(done = done) else t
            }
            mutate { api -> api.completeTodayTask(TaskCompleteRequest(text, done)) }
        }
    }

    fun delete(text: String) {
        viewModelScope.launch {
            _tasks.value = _tasks.value.filterNot { it.text == text }
            mutate { api -> api.deleteTodayTask(TaskTextRequest(text)) }
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
            _tasks.value = api.listTodayTasks().items
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
}
