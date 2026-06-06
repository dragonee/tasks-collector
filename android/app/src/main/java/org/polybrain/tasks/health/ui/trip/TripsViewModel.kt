package org.polybrain.tasks.health.ui.trip

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import org.polybrain.tasks.health.data.Settings
import org.polybrain.tasks.health.data.SettingsSnapshot
import org.polybrain.tasks.health.data.TasksApi
import org.polybrain.tasks.health.data.TasksClient
import org.polybrain.tasks.health.data.TripStartRequest
import org.polybrain.tasks.health.data.TripSummary
import org.polybrain.tasks.health.location.TripTracker

class TripsViewModel(application: Application) : AndroidViewModel(application) {

    private val settings = Settings(application)

    private val _active = MutableStateFlow<List<TripSummary>>(emptyList())
    val active: StateFlow<List<TripSummary>> = _active.asStateFlow()

    private val _history = MutableStateFlow<List<TripSummary>>(emptyList())
    val history: StateFlow<List<TripSummary>> = _history.asStateFlow()

    private val _totalHistory = MutableStateFlow(0)
    val totalHistory: StateFlow<Int> = _totalHistory.asStateFlow()

    private val _loading = MutableStateFlow(false)
    val loading: StateFlow<Boolean> = _loading.asStateFlow()

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    private val _configured = MutableStateFlow(false)
    val configured: StateFlow<Boolean> = _configured.asStateFlow()

    /** When non-null, the UI should navigate to this trip's detail screen. */
    private val _focusTrip = MutableStateFlow<Long?>(null)
    val focusTrip: StateFlow<Long?> = _focusTrip.asStateFlow()

    private var historyPage = 1
    private val pageSize = 20
    private var autoFocusedOnce = false

    fun refresh() {
        viewModelScope.launch { reload() }
    }

    fun startTrip() {
        viewModelScope.launch {
            val snapshot = ensureConfigured() ?: return@launch
            _loading.value = true
            try {
                val api = buildApi(snapshot)
                val story = api.startTrip(TripStartRequest()).story
                _focusTrip.value = story.id
                // Begin recording the location breadcrumb trail for this trip.
                TripTracker.start(getApplication(), story.id)
                reload()
            } catch (t: Throwable) {
                _error.value = t.message ?: t.javaClass.simpleName
            } finally {
                _loading.value = false
            }
        }
    }

    fun openTrip(storyId: Long) {
        _focusTrip.value = storyId
    }

    fun onFocusConsumed() {
        _focusTrip.value = null
    }

    fun loadMoreHistory() {
        viewModelScope.launch {
            val snapshot = ensureConfigured() ?: return@launch
            historyPage += 1
            _loading.value = true
            try {
                val api = buildApi(snapshot)
                val page = api.listTrips(page = historyPage, pageSize = pageSize)
                _history.value = _history.value + page.history
                _totalHistory.value = page.totalHistory
            } catch (t: Throwable) {
                historyPage -= 1
                _error.value = t.message ?: t.javaClass.simpleName
            } finally {
                _loading.value = false
            }
        }
    }

    fun clearError() {
        _error.value = null
    }

    private suspend fun reload() {
        val snapshot = settings.snapshot()
        _configured.value = snapshot.isConfigured
        if (!snapshot.isConfigured) {
            _active.value = emptyList()
            _history.value = emptyList()
            _totalHistory.value = 0
            return
        }
        _loading.value = true
        try {
            val api = buildApi(snapshot)
            historyPage = 1
            val page = api.listTrips(page = 1, pageSize = pageSize)
            _active.value = page.active
            _history.value = page.history
            _totalHistory.value = page.totalHistory
            _error.value = null
            // Align tracking with the server: a trip stopped elsewhere (e.g.
            // the web) turns the breadcrumb service off; an active one keeps it on.
            TripTracker.reconcile(getApplication(), page.active.map { it.id })
            // On first successful load only, if exactly one active trip
            // exists, hop the user straight into it. Subsequent refreshes
            // leave them on the list so back-navigation works.
            if (!autoFocusedOnce && page.active.size == 1) {
                _focusTrip.value = page.active.first().id
            }
            autoFocusedOnce = true
        } catch (t: Throwable) {
            _error.value = t.message ?: t.javaClass.simpleName
        } finally {
            _loading.value = false
        }
    }

    private suspend fun ensureConfigured(): SettingsSnapshot? {
        val snapshot = settings.snapshot()
        _configured.value = snapshot.isConfigured
        if (!snapshot.isConfigured) {
            _error.value = "Configure server URL and API token first."
            return null
        }
        return snapshot
    }

    private fun buildApi(snapshot: SettingsSnapshot): TasksApi =
        TasksClient.build(snapshot.serverUrl, snapshot.apiToken)
}
