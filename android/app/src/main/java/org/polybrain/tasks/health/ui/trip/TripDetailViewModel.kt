package org.polybrain.tasks.health.ui.trip

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import java.time.OffsetDateTime
import java.util.Locale
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import org.polybrain.tasks.health.data.Settings
import org.polybrain.tasks.health.data.SettingsSnapshot
import org.polybrain.tasks.health.data.TasksApi
import org.polybrain.tasks.health.data.TasksClient
import org.polybrain.tasks.health.data.TripDetailResponse
import org.polybrain.tasks.health.data.TripEvent
import org.polybrain.tasks.health.data.TripNoteRequest
import org.polybrain.tasks.health.data.TripStoryIdRequest
import org.polybrain.tasks.health.data.TripSummary
import org.polybrain.tasks.health.data.TripUpdateRequest
import org.polybrain.tasks.health.location.LocationFix
import org.polybrain.tasks.health.location.LocationProvider

class TripDetailViewModel(application: Application) : AndroidViewModel(application) {

    private val settings = Settings(application)
    private val locationProvider = LocationProvider(application)

    private val _story = MutableStateFlow<TripSummary?>(null)
    val story: StateFlow<TripSummary?> = _story.asStateFlow()

    private val _events = MutableStateFlow<List<TripEvent>>(emptyList())
    val events: StateFlow<List<TripEvent>> = _events.asStateFlow()

    private val _loading = MutableStateFlow(false)
    val loading: StateFlow<Boolean> = _loading.asStateFlow()

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    /** Open/closed state for the add-note dialog. */
    private val _noteDialogOpen = MutableStateFlow(false)
    val noteDialogOpen: StateFlow<Boolean> = _noteDialogOpen.asStateFlow()

    /**
     * GPS resolution state. The dialog reads this to decide whether to
     * gate the Send button and what hint to show.
     */
    sealed class GpsState {
        object Idle : GpsState()
        object Waiting : GpsState()
        data class Ready(val fix: LocationFix) : GpsState()
        object Denied : GpsState()
        object Unavailable : GpsState()
    }

    private val _gps = MutableStateFlow<GpsState>(GpsState.Idle)
    val gps: StateFlow<GpsState> = _gps.asStateFlow()

    /** Whether the user has explicitly opted to send without location. */
    private val _allowNoLocation = MutableStateFlow(false)
    val allowNoLocation: StateFlow<Boolean> = _allowNoLocation.asStateFlow()

    private val _renameOpen = MutableStateFlow(false)
    val renameOpen: StateFlow<Boolean> = _renameOpen.asStateFlow()

    private var storyId: Long = -1

    fun load(id: Long) {
        if (id == storyId && _story.value != null) return
        storyId = id
        refresh()
    }

    fun refresh() {
        viewModelScope.launch { reload() }
    }

    fun openAddNote() {
        _allowNoLocation.value = false
        _gps.value = GpsState.Waiting
        _noteDialogOpen.value = true
        viewModelScope.launch {
            if (!locationProvider.hasFineLocationPermission()) {
                _gps.value = GpsState.Denied
                return@launch
            }
            val fix = locationProvider.currentFix()
            _gps.value = if (fix != null) GpsState.Ready(fix) else GpsState.Unavailable
        }
    }

    fun closeAddNote() {
        _noteDialogOpen.value = false
        _gps.value = GpsState.Idle
        _allowNoLocation.value = false
    }

    fun setAllowNoLocation(value: Boolean) {
        _allowNoLocation.value = value
    }

    /** Called by the screen after the runtime permission request finishes. */
    fun onLocationPermissionResult(granted: Boolean) {
        if (!_noteDialogOpen.value) return
        if (!granted) {
            _gps.value = GpsState.Denied
            return
        }
        _gps.value = GpsState.Waiting
        viewModelScope.launch {
            val fix = locationProvider.currentFix()
            _gps.value = if (fix != null) GpsState.Ready(fix) else GpsState.Unavailable
        }
    }

    fun sendNote(text: String) {
        val story = _story.value ?: return
        if (story.stopped != null) return
        val gpsState = _gps.value
        val fix = (gpsState as? GpsState.Ready)?.fix
        if (fix == null && !_allowNoLocation.value) return

        val comment = composeComment(fix, text)
        val published = OffsetDateTime.now().toString()
        _noteDialogOpen.value = false
        _gps.value = GpsState.Idle
        _allowNoLocation.value = false

        viewModelScope.launch {
            val snapshot = ensureConfigured() ?: return@launch
            try {
                val api = buildApi(snapshot)
                api.addTripNote(
                    TripNoteRequest(
                        storyId = story.id,
                        comment = comment,
                        published = published,
                    )
                )
                reload()
            } catch (t: Throwable) {
                _error.value = t.message ?: t.javaClass.simpleName
            }
        }
    }

    fun stop() {
        val story = _story.value ?: return
        if (story.stopped != null) return
        viewModelScope.launch {
            val snapshot = ensureConfigured() ?: return@launch
            try {
                val api = buildApi(snapshot)
                api.stopTrip(TripStoryIdRequest(storyId = story.id))
                reload()
            } catch (t: Throwable) {
                _error.value = t.message ?: t.javaClass.simpleName
            }
        }
    }

    fun openRename() {
        _renameOpen.value = true
    }

    fun closeRename() {
        _renameOpen.value = false
    }

    fun rename(newTitle: String) {
        val story = _story.value ?: return
        val trimmed = newTitle.trim()
        if (trimmed.isEmpty() || trimmed == story.title) {
            _renameOpen.value = false
            return
        }
        _renameOpen.value = false
        viewModelScope.launch {
            val snapshot = ensureConfigured() ?: return@launch
            try {
                val api = buildApi(snapshot)
                api.updateTrip(TripUpdateRequest(storyId = story.id, title = trimmed))
                reload()
            } catch (t: Throwable) {
                _error.value = t.message ?: t.javaClass.simpleName
            }
        }
    }

    fun clearError() {
        _error.value = null
    }

    private suspend fun reload() {
        if (storyId <= 0) return
        val snapshot = ensureConfigured() ?: return
        _loading.value = true
        try {
            val api = buildApi(snapshot)
            val detail: TripDetailResponse = api.tripDetail(storyId)
            _story.value = detail.story
            _events.value = detail.events
            _error.value = null
        } catch (t: Throwable) {
            _error.value = t.message ?: t.javaClass.simpleName
        } finally {
            _loading.value = false
        }
    }

    private suspend fun ensureConfigured(): SettingsSnapshot? {
        val snapshot = settings.snapshot()
        if (!snapshot.isConfigured) {
            _error.value = "Configure server URL and API token first."
            return null
        }
        return snapshot
    }

    private fun buildApi(snapshot: SettingsSnapshot): TasksApi =
        TasksClient.build(snapshot.serverUrl, snapshot.apiToken)

    companion object {
        internal fun composeComment(fix: LocationFix?, text: String): String {
            val trimmed = text.trim()
            return if (fix != null) {
                val prefix = String.format(
                    Locale.US, "#poi lat=%.6f lng=%.6f", fix.lat, fix.lng,
                )
                if (trimmed.isEmpty()) prefix else "$prefix\n$trimmed"
            } else {
                trimmed
            }
        }
    }
}
