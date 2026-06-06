package org.polybrain.tasks.health.ui.trip

import android.app.Application
import android.net.Uri
import android.provider.MediaStore
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import androidx.work.WorkInfo
import androidx.work.WorkManager
import java.io.File
import java.io.IOException
import java.time.Instant
import java.time.OffsetDateTime
import java.time.ZoneId
import java.util.Locale
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.polybrain.tasks.health.data.BreadcrumbStore
import org.polybrain.tasks.health.data.Outbox
import org.polybrain.tasks.health.data.OutboxItem
import org.polybrain.tasks.health.data.Settings
import org.polybrain.tasks.health.data.SettingsSnapshot
import org.polybrain.tasks.health.data.TasksApi
import org.polybrain.tasks.health.data.TasksClient
import org.polybrain.tasks.health.data.TripDetailResponse
import org.polybrain.tasks.health.data.TripEvent
import org.polybrain.tasks.health.data.TripStoryIdRequest
import org.polybrain.tasks.health.data.TripSummary
import org.polybrain.tasks.health.data.TripUpdateRequest
import org.polybrain.tasks.health.location.LocationFix
import org.polybrain.tasks.health.location.LocationProvider
import org.polybrain.tasks.health.location.PhotoLocationResolver
import org.polybrain.tasks.health.location.TripTracker
import org.polybrain.tasks.health.sync.SyncScheduler

class TripDetailViewModel(application: Application) : AndroidViewModel(application) {

    private val settings = Settings(application)
    private val locationProvider = LocationProvider(application)
    private val outbox = Outbox(application)
    private val breadcrumbStore = BreadcrumbStore(application)
    private val workManager = WorkManager.getInstance(application)

    private val _story = MutableStateFlow<TripSummary?>(null)
    val story: StateFlow<TripSummary?> = _story.asStateFlow()

    private val _events = MutableStateFlow<List<TripEvent>>(emptyList())
    val events: StateFlow<List<TripEvent>> = _events.asStateFlow()

    /** Trip writes still in the local outbox (waiting / syncing / failed). */
    private val _pending = MutableStateFlow<List<OutboxItem>>(emptyList())
    val pending: StateFlow<List<OutboxItem>> = _pending.asStateFlow()

    /** True while the outbox drain worker is actively running. */
    private val _syncing = MutableStateFlow(false)
    val syncing: StateFlow<Boolean> = _syncing.asStateFlow()

    /**
     * Server events and local pending items merged into one chronological list
     * (newest first), so a just-queued note/photo shows in the timeline before
     * it ever reaches the server.
     */
    val timeline: StateFlow<List<TimelineRow>> =
        combine(_events, _pending) { events, pending ->
            (events.map { TimelineRow.Synced(it) } + pending.map { TimelineRow.Pending(it) })
                .sortedByDescending { instantOf(it.publishedIso) }
        }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

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

    /** Presigned URL for the full-size original being viewed (null = closed). */
    private val _viewerUrl = MutableStateFlow<String?>(null)
    val viewerUrl: StateFlow<String?> = _viewerUrl.asStateFlow()

    /**
     * GPS resolution state. The dialog reads this to decide whether to
     * gate the Send button and what hint to show.
     */
    /** Where a Ready fix came from: a live GPS read (notes) or the trip's recorded track (photos). */
    enum class GpsSource { LIVE, TRACK }

    sealed class GpsState {
        object Idle : GpsState()
        object Waiting : GpsState()
        data class Ready(
            val fix: LocationFix,
            val source: GpsSource = GpsSource.LIVE,
            // For TRACK: the photo's capture time, shown in the dialog hint.
            val atMillis: Long? = null,
        ) : GpsState()
        object Denied : GpsState()
        object Unavailable : GpsState()
    }

    private val _gps = MutableStateFlow<GpsState>(GpsState.Idle)
    val gps: StateFlow<GpsState> = _gps.asStateFlow()

    private val _renameOpen = MutableStateFlow(false)
    val renameOpen: StateFlow<Boolean> = _renameOpen.asStateFlow()

    private var storyId: Long = -1

    init {
        // Track the drain worker: keep the pending list fresh, drive the
        // "Syncing…" label, and reload server events when a drain completes
        // (so synced items flip from pending → real timeline rows).
        viewModelScope.launch {
            var wasRunning = false
            workManager.getWorkInfosForUniqueWorkFlow(SyncScheduler.OUTBOX).collect { infos ->
                val running = infos.any { it.state == WorkInfo.State.RUNNING }
                _syncing.value = running
                refreshPending()
                if (wasRunning && !running) reloadIfLoaded()
                wasRunning = running
            }
        }
    }

    fun load(id: Long) {
        if (id == storyId && _story.value != null) return
        storyId = id
        refresh()
    }

    fun refresh() {
        viewModelScope.launch {
            reload()
            refreshPending()
        }
    }

    fun openAddNote() {
        _noteDialogOpen.value = true
        startGpsResolution()
    }

    fun closeAddNote() {
        _noteDialogOpen.value = false
        _gps.value = GpsState.Idle
    }

    /**
     * Open the add-photo dialog for a picked image. Unlike a note, a photo's
     * location comes from the trip's recorded breadcrumb trail at the photo's
     * capture time (so an old photo gets where it was *taken*, not where you
     * are now) — never a fresh fix.
     */
    fun openAddPhoto(uri: Uri) {
        _selectedPhoto.value = uri
        _photoDialogOpen.value = true
        _gps.value = GpsState.Waiting
        viewModelScope.launch {
            val captureMs = withContext(Dispatchers.IO) {
                captureMillisFor(uri) ?: System.currentTimeMillis()
            }
            val fix = withContext(Dispatchers.IO) {
                PhotoLocationResolver.resolve(breadcrumbStore.all(), captureMs)
            }
            _gps.value = if (fix != null) {
                GpsState.Ready(fix, GpsSource.TRACK, captureMs)
            } else {
                // No trusted track location for this photo's time — only plain
                // "Send" (without location) will be offered.
                GpsState.Unavailable
            }
        }
    }

    fun closeAddPhoto() {
        _photoDialogOpen.value = false
        _selectedPhoto.value = null
        _gps.value = GpsState.Idle
    }

    /** Live GPS bootstrap for the note dialog (a note is recorded "now"). */
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

    /**
     * Enqueue a note. [includeLocation] is the explicit "Save with location"
     * choice — the default "Send" attaches no `#poi`, so location lands only on
     * notes where it's actually wanted.
     */
    fun sendNote(text: String, includeLocation: Boolean) {
        val story = _story.value ?: return
        if (story.stopped != null) return
        val fix = if (includeLocation) (_gps.value as? GpsState.Ready)?.fix else null

        val comment = composeComment(fix, text)
        // A note needs content; without a location line that means some text.
        if (comment.isBlank()) return
        val published = OffsetDateTime.now().toString()
        _noteDialogOpen.value = false
        _gps.value = GpsState.Idle

        // Queue locally and kick the drain; the item shows immediately and the
        // worker delivers it (now or when connectivity returns).
        viewModelScope.launch {
            withContext(Dispatchers.IO) { outbox.enqueueNote(story.id, comment, published) }
            refreshPending()
            SyncScheduler.drainOutbox(getApplication())
        }
    }

    /** Enqueue a photo. [includeLocation] mirrors [sendNote] (the track fix). */
    fun sendPhoto(text: String, includeLocation: Boolean) {
        val story = _story.value ?: return
        if (story.stopped != null) return
        val uri = _selectedPhoto.value ?: return
        val fix = if (includeLocation) (_gps.value as? GpsState.Ready)?.fix else null

        val comment = composeComment(fix, text)
        // Close the dialog now; copy + enqueue happen in the background.
        _photoDialogOpen.value = false
        _selectedPhoto.value = null
        _gps.value = GpsState.Idle

        viewModelScope.launch {
            try {
                val resolver = getApplication<Application>().contentResolver
                val contentType = resolver.getType(uri) ?: "image/jpeg"
                // Read the bytes NOW — the picker's content Uri is only readable
                // for this session, so they must be copied before we lose access.
                val bytes = withContext(Dispatchers.IO) {
                    resolver.openInputStream(uri)?.use { it.readBytes() }
                } ?: throw IOException("could not read the selected photo")
                val published = withContext(Dispatchers.IO) { captureTimeFor(uri) }
                withContext(Dispatchers.IO) {
                    outbox.enqueuePhoto(story.id, comment, published, contentType, bytes)
                }
                refreshPending()
                SyncScheduler.drainOutbox(getApplication())
            } catch (t: Throwable) {
                _error.value = t.message ?: t.javaClass.simpleName
            }
        }
    }

    /** Re-queue a permanently-failed item for another delivery attempt. */
    fun retry(item: OutboxItem) {
        viewModelScope.launch {
            withContext(Dispatchers.IO) {
                outbox.update(item.copy(failedPermanently = false, lastError = null))
            }
            refreshPending()
            SyncScheduler.drainOutbox(getApplication())
        }
    }

    /** Drop a queued item (and its photo file) without sending it. */
    fun discard(item: OutboxItem) {
        viewModelScope.launch {
            withContext(Dispatchers.IO) { outbox.remove(item) }
            refreshPending()
        }
    }

    /** Local file backing a pending photo, for the timeline thumbnail. */
    fun pendingPhotoFile(item: OutboxItem): File? = outbox.photoFile(item)

    /**
     * Best-effort capture time of a picked image: the gallery's DATE_TAKEN
     * (epoch millis, UTC) when present, else now. The backend overrides this
     * with the original's EXIF DateTimeOriginal when the file carries one.
     */
    private fun captureTimeFor(uri: Uri): String {
        val millis = captureMillisFor(uri)
        return if (millis != null) {
            OffsetDateTime.ofInstant(
                Instant.ofEpochMilli(millis),
                ZoneId.systemDefault(),
            ).toString()
        } else {
            OffsetDateTime.now().toString()
        }
    }

    /** The gallery's DATE_TAKEN (epoch millis), or null when absent. */
    private fun captureMillisFor(uri: Uri): Long? {
        val resolver = getApplication<Application>().contentResolver
        return runCatching {
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
        }.getOrNull()?.takeIf { it > 0 }
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
                // Stop recording the breadcrumb trail for this trip.
                TripTracker.stop(getApplication(), story.id)
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

    private fun reloadIfLoaded() {
        if (storyId > 0) viewModelScope.launch { reload() }
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

    private suspend fun refreshPending() {
        _pending.value = if (storyId <= 0) {
            emptyList()
        } else {
            withContext(Dispatchers.IO) { outbox.forStory(storyId) }
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

    /** One row in the merged timeline: either a server event or a queued item. */
    sealed class TimelineRow {
        abstract val publishedIso: String

        data class Synced(val event: TripEvent) : TimelineRow() {
            override val publishedIso: String get() = event.published
        }

        data class Pending(val item: OutboxItem) : TimelineRow() {
            override val publishedIso: String get() = item.published
        }
    }

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

        private fun instantOf(iso: String): Instant =
            runCatching { OffsetDateTime.parse(iso).toInstant() }.getOrDefault(Instant.EPOCH)
    }
}
