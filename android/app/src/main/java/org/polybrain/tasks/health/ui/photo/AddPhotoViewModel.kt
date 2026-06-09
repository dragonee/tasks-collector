package org.polybrain.tasks.health.ui.photo

import android.app.Application
import android.net.Uri
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import java.io.IOException
import java.time.OffsetDateTime
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.polybrain.tasks.health.data.Outbox
import org.polybrain.tasks.health.location.GpsState
import org.polybrain.tasks.health.location.LocationProvider
import org.polybrain.tasks.health.location.composeComment
import org.polybrain.tasks.health.sync.SyncScheduler

/**
 * Drives the standalone "Add Photo" flow opened from the main-screen FAB: a
 * photo queued with **no** trip (a storyless `PhotoTaken`), an optional note,
 * and an optional **live** GPS fix — there is no trip track to resolve against,
 * so unlike [org.polybrain.tasks.health.ui.trip.TripDetailViewModel] the
 * location always comes from a fresh fix taken "now".
 *
 * The photo is enqueued with `storyId = null`; [org.polybrain.tasks.health.sync.OutboxDrainer]
 * then delivers it through the storyless `photo/…` endpoints.
 */
class AddPhotoViewModel(application: Application) : AndroidViewModel(application) {

    private val locationProvider = LocationProvider(application)
    private val outbox = Outbox(application)

    /** Open/closed state for the add-photo dialog and the picked image. */
    private val _dialogOpen = MutableStateFlow(false)
    val dialogOpen: StateFlow<Boolean> = _dialogOpen.asStateFlow()

    private val _selectedPhoto = MutableStateFlow<Uri?>(null)
    val selectedPhoto: StateFlow<Uri?> = _selectedPhoto.asStateFlow()

    private val _gps = MutableStateFlow<GpsState>(GpsState.Idle)
    val gps: StateFlow<GpsState> = _gps.asStateFlow()

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    /** Open the dialog for a picked image and start resolving a live GPS fix. */
    fun openAddPhoto(uri: Uri) {
        _selectedPhoto.value = uri
        _dialogOpen.value = true
        startGpsResolution()
    }

    fun closeAddPhoto() {
        _dialogOpen.value = false
        _selectedPhoto.value = null
        _gps.value = GpsState.Idle
    }

    private fun startGpsResolution() {
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

    /** Called by the screen after the runtime permission request finishes. */
    fun onLocationPermissionResult(granted: Boolean) {
        if (!_dialogOpen.value) return
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

    /**
     * Enqueue the photo with no story. [includeLocation] is the explicit "Save
     * with location" choice; the default "Send" attaches no `#poi`. Bytes are
     * read now because the picker's content `Uri` is only readable this session.
     */
    fun sendPhoto(text: String, includeLocation: Boolean) {
        val uri = _selectedPhoto.value ?: return
        val fix = if (includeLocation) (_gps.value as? GpsState.Ready)?.fix else null
        val comment = composeComment(fix, text)
        // A standalone photo is timestamped when it's added (now), not by the
        // image's capture/EXIF time — unlike a trip photo.
        val published = OffsetDateTime.now().toString()
        _dialogOpen.value = false
        _selectedPhoto.value = null
        _gps.value = GpsState.Idle

        viewModelScope.launch {
            try {
                val resolver = getApplication<Application>().contentResolver
                val contentType = resolver.getType(uri) ?: "image/jpeg"
                val bytes = withContext(Dispatchers.IO) {
                    resolver.openInputStream(uri)?.use { it.readBytes() }
                } ?: throw IOException("could not read the selected photo")
                withContext(Dispatchers.IO) {
                    // storyId = null -> delivered through the storyless endpoints.
                    outbox.enqueuePhoto(null, comment, published, contentType, bytes)
                }
                SyncScheduler.drainOutbox(getApplication())
            } catch (t: Throwable) {
                _error.value = t.message ?: t.javaClass.simpleName
            }
        }
    }

    fun clearError() {
        _error.value = null
    }
}
