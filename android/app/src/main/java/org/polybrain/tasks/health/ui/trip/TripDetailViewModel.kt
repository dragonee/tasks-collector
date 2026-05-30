package org.polybrain.tasks.health.ui.trip

import android.app.Application
import android.net.Uri
import android.provider.MediaStore
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import java.io.IOException
import java.time.Instant
import java.time.OffsetDateTime
import java.time.ZoneId
import java.util.Locale
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.polybrain.tasks.health.data.PhotoConfirmRequest
import org.polybrain.tasks.health.data.PhotoPresignRequest
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

    /** Open/closed state for the add-photo dialog and the picked image. */
    private val _photoDialogOpen = MutableStateFlow(false)
    val photoDialogOpen: StateFlow<Boolean> = _photoDialogOpen.asStateFlow()

    private val _selectedPhoto = MutableStateFlow<Uri?>(null)
    val selectedPhoto: StateFlow<Uri?> = _selectedPhoto.asStateFlow()

    /** True while a photo is being uploaded + confirmed. */
    private val _uploading = MutableStateFlow(false)
    val uploading: StateFlow<Boolean> = _uploading.asStateFlow()

    /** Presigned URL for the full-size original being viewed (null = closed). */
    private val _viewerUrl = MutableStateFlow<String?>(null)
    val viewerUrl: StateFlow<String?> = _viewerUrl.asStateFlow()

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
        _noteDialogOpen.value = true
        startGpsResolution()
    }

    fun closeAddNote() {
        _noteDialogOpen.value = false
        _gps.value = GpsState.Idle
        _allowNoLocation.value = false
    }

    /** Open the add-photo dialog for a picked image and resolve GPS. */
    fun openAddPhoto(uri: Uri) {
        _selectedPhoto.value = uri
        _photoDialogOpen.value = true
        startGpsResolution()
    }

    fun closeAddPhoto() {
        if (_uploading.value) return
        _photoDialogOpen.value = false
        _selectedPhoto.value = null
        _gps.value = GpsState.Idle
        _allowNoLocation.value = false
    }

    /** Shared GPS bootstrap used by both the note and photo dialogs. */
    private fun startGpsResolution() {
        _allowNoLocation.value = false
        _gps.value = GpsState.Waiting
        viewModelScope.launch {
            if (!locationProvider.hasFineLocationPermission()) {
                _gps.value = GpsState.Denied
                return@launch
            }
            val fix = locationProvider.currentFix()
            _gps.value = if (fix != null) GpsState.Ready(fix) else GpsState.Unavailable
        }
    }

    fun setAllowNoLocation(value: Boolean) {
        _allowNoLocation.value = value
    }

    /** Called by the screen after the runtime permission request finishes. */
    fun onLocationPermissionResult(granted: Boolean) {
        if (!_noteDialogOpen.value && !_photoDialogOpen.value) return
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

    fun sendPhoto(text: String) {
        val story = _story.value ?: return
        if (story.stopped != null) return
        val uri = _selectedPhoto.value ?: return
        val gpsState = _gps.value
        val fix = (gpsState as? GpsState.Ready)?.fix
        if (fix == null && !_allowNoLocation.value) return

        val comment = composeComment(fix, text)
        _uploading.value = true

        viewModelScope.launch {
            val snapshot = ensureConfigured()
            if (snapshot == null) {
                _uploading.value = false
                return@launch
            }
            try {
                val resolver = getApplication<Application>().contentResolver
                val contentType = resolver.getType(uri) ?: "image/jpeg"
                val bytes = withContext(Dispatchers.IO) {
                    resolver.openInputStream(uri)?.use { it.readBytes() }
                } ?: throw IOException("could not read the selected photo")
                // Timestamp the photo with when it was taken, not now. The
                // backend further overrides this with the original's EXIF
                // DateTimeOriginal when present.
                val published = withContext(Dispatchers.IO) { captureTimeFor(uri) }

                val api = buildApi(snapshot)
                val presign = api.presignPhoto(
                    PhotoPresignRequest(storyId = story.id, contentType = contentType)
                )
                withContext(Dispatchers.IO) {
                    TasksClient.putToPresignedUrl(presign.uploadUrl, bytes, contentType)
                }
                api.addTripPhoto(
                    PhotoConfirmRequest(
                        storyId = story.id,
                        key = presign.key,
                        comment = comment,
                        contentType = contentType,
                        published = published,
                    )
                )
                _photoDialogOpen.value = false
                _selectedPhoto.value = null
                _gps.value = GpsState.Idle
                _allowNoLocation.value = false
                reload()
            } catch (t: Throwable) {
                _error.value = t.message ?: t.javaClass.simpleName
            } finally {
                _uploading.value = false
            }
        }
    }

    /**
     * Best-effort capture time of a picked image: the gallery's DATE_TAKEN
     * (epoch millis, UTC) when present, else now. The backend overrides this
     * with the original's EXIF DateTimeOriginal when the file carries one.
     */
    private fun captureTimeFor(uri: Uri): String {
        val resolver = getApplication<Application>().contentResolver
        val millis = runCatching {
            resolver.query(
                uri,
                arrayOf(MediaStore.Images.Media.DATE_TAKEN),
                null,
                null,
                null,
            )?.use { cursor ->
                val index = cursor.getColumnIndex(MediaStore.Images.Media.DATE_TAKEN)
                if (index >= 0 && cursor.moveToFirst() && !cursor.isNull(index)) {
                    cursor.getLong(index)
                } else {
                    null
                }
            }
        }.getOrNull()
        return if (millis != null && millis > 0) {
            OffsetDateTime.ofInstant(
                Instant.ofEpochMilli(millis),
                ZoneId.systemDefault(),
            ).toString()
        } else {
            OffsetDateTime.now().toString()
        }
    }

    /** Fetch a fresh presigned URL for a photo's original and open the viewer. */
    fun openPhoto(eventId: Long) {
        viewModelScope.launch {
            val snapshot = ensureConfigured() ?: return@launch
            try {
                val api = buildApi(snapshot)
                _viewerUrl.value = api.photoOriginal(eventId).url
            } catch (t: Throwable) {
                _error.value = t.message ?: t.javaClass.simpleName
            }
        }
    }

    fun closeViewer() {
        _viewerUrl.value = null
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
