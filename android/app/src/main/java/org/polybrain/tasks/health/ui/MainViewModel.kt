package org.polybrain.tasks.health.ui

import android.app.Application
import androidx.health.connect.client.HealthConnectClient
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import org.polybrain.tasks.health.data.DailyMetrics
import org.polybrain.tasks.health.data.HealthRepository
import org.polybrain.tasks.health.data.Settings
import org.polybrain.tasks.health.data.SettingsSnapshot
import org.polybrain.tasks.health.data.TasksClient
import org.polybrain.tasks.health.data.TrackHabitTextRequest
import org.polybrain.tasks.health.sync.SyncScheduler
import java.time.LocalDate
import java.time.OffsetDateTime
import java.time.ZoneId
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

/**
 * The activities the FAB on the Health screen can register, each mapped to the
 * hashtag the backend parses into a [HabitTracked]. [Gym] is the default
 * subtype. The keyword is sent verbatim (Unicode is fine) prefixed with '#'.
 */
enum class ActivityType(val keyword: String) {
    Gym("siłka"),
    Workout("workout"),
}

class MainViewModel(application: Application) : AndroidViewModel(application) {

    private val settings = Settings(application)
    private val health = HealthRepository(application)

    val settingsState: StateFlow<SettingsSnapshot> = settings.flow.stateIn(
        viewModelScope,
        SharingStarted.WhileSubscribed(5_000),
        SettingsSnapshot("", "", 0L, ""),
    )

    private val _permissionsGranted = MutableStateFlow(false)
    val permissionsGranted: StateFlow<Boolean> = _permissionsGranted.asStateFlow()

    private val _todayMetrics = MutableStateFlow<DailyMetrics?>(null)
    val todayMetrics: StateFlow<DailyMetrics?> = _todayMetrics.asStateFlow()

    /** Open/closed state for the "register activity" dialog opened from the FAB. */
    private val _activityDialogOpen = MutableStateFlow(false)
    val activityDialogOpen: StateFlow<Boolean> = _activityDialogOpen.asStateFlow()

    /** True while an activity is being posted; gates the dialog buttons. */
    private val _activitySaving = MutableStateFlow(false)
    val activitySaving: StateFlow<Boolean> = _activitySaving.asStateFlow()

    /** Last activity-post error, shown inline in the dialog (null = none). */
    private val _activityError = MutableStateFlow<String?>(null)
    val activityError: StateFlow<String?> = _activityError.asStateFlow()

    val healthConnectStatus: Int = health.availability()
    val requiredPermissions: Set<String> = health.permissions

    init {
        // Resume any trip notes/photos queued offline in a previous session.
        // The worker no-ops when unconfigured, so this is safe to call always.
        SyncScheduler.drainOutbox(application)
        viewModelScope.launch {
            refreshPermissionState()
            if (_permissionsGranted.value) refreshMetrics()
        }
    }

    suspend fun refreshPermissionState() {
        val granted = healthConnectStatus == HealthConnectClient.SDK_AVAILABLE &&
            runCatching { health.hasAllPermissions() }.getOrDefault(false)
        val flipped = !_permissionsGranted.value && granted
        _permissionsGranted.value = granted
        if (flipped) refreshMetrics()
    }

    fun refreshMetricsAsync() {
        viewModelScope.launch { refreshMetrics() }
    }

    private suspend fun refreshMetrics() {
        if (!_permissionsGranted.value) return
        val today = LocalDate.now(ZoneId.systemDefault())
        _todayMetrics.value = runCatching { health.aggregateDay(today) }.getOrNull()
    }

    fun save(serverUrl: String, apiToken: String) {
        viewModelScope.launch {
            settings.saveServerConfig(serverUrl, apiToken)
            SyncScheduler.schedule(getApplication())
        }
    }

    fun syncNow() {
        SyncScheduler.runOnce(getApplication())
        refreshMetricsAsync()
    }

    fun openActivityDialog() {
        _activityError.value = null
        _activityDialogOpen.value = true
    }

    fun closeActivityDialog() {
        if (_activitySaving.value) return
        _activityDialogOpen.value = false
    }

    /**
     * Posts a single `#keyword note` line through the non-idempotent text
     * endpoint, which creates one [HabitTracked] per parsed hashtag. Unlike a
     * trip note this records no JournalAdded — it is purely the habit entry.
     * Multiple posts on the same day are intentional (e.g. two gym visits).
     */
    fun trackActivity(type: ActivityType, note: String) {
        if (_activitySaving.value) return
        val trimmed = note.trim()
        val text = if (trimmed.isEmpty()) "#${type.keyword}" else "#${type.keyword} $trimmed"
        // Wall-clock moment of the tap, so the entry lands on today.
        val published = OffsetDateTime.now().toString()
        _activitySaving.value = true
        _activityError.value = null
        viewModelScope.launch {
            val snapshot = settings.snapshot()
            if (!snapshot.isConfigured) {
                _activityError.value = "Configure server URL and API token first."
                _activitySaving.value = false
                return@launch
            }
            try {
                val api = TasksClient.build(snapshot.serverUrl, snapshot.apiToken)
                api.trackHabitText(TrackHabitTextRequest(text = text, published = published))
                _activityDialogOpen.value = false
            } catch (t: Throwable) {
                _activityError.value = t.message ?: t.javaClass.simpleName
            } finally {
                _activitySaving.value = false
            }
        }
    }
}
