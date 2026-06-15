package org.polybrain.tasks.health.ui

import android.app.Application
import androidx.health.connect.client.HealthConnectClient
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import org.polybrain.tasks.health.data.DailyMetrics
import org.polybrain.tasks.health.data.HealthDataResponse
import org.polybrain.tasks.health.data.HealthRepository
import org.polybrain.tasks.health.data.Settings
import org.polybrain.tasks.health.data.SettingsSnapshot
import org.polybrain.tasks.health.data.TasksClient
import org.polybrain.tasks.health.data.TrackHabitTextRequest
import org.polybrain.tasks.health.location.TripTracker
import org.polybrain.tasks.health.sync.SyncScheduler
import java.time.LocalDate
import java.time.OffsetDateTime
import java.time.ZoneId
import java.util.Locale
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
 *
 * [Weight] is special: instead of a free-text note it carries a numeric
 * kilogram value, posted as `#weight weight=<x.x>kg` (see [MainViewModel.trackWeight]).
 */
enum class ActivityType(val keyword: String) {
    Gym("siłka"),
    Workout("workout"),
    Weight("weight"),
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

    /** Server-derived health data (last recorded weight); null until loaded. */
    private val _healthData = MutableStateFlow<HealthDataResponse?>(null)
    val healthData: StateFlow<HealthDataResponse?> = _healthData.asStateFlow()

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
            // Resume location tracking if a trip was being tracked before the
            // app was killed (the foreground service doesn't survive that).
            TripTracker.resumeIfNeeded(getApplication())
            refreshPermissionState()
            if (_permissionsGranted.value) refreshMetrics()
            refreshHealthData()
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

    fun refreshHealthDataAsync() {
        viewModelScope.launch { refreshHealthData() }
    }

    private suspend fun refreshHealthData() {
        val snapshot = settings.snapshot()
        if (!snapshot.isConfigured) return
        val data = runCatching {
            TasksClient.build(snapshot.serverUrl, snapshot.apiToken).healthData()
        }.getOrNull()
        if (data != null) _healthData.value = data
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
        refreshHealthDataAsync()
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
        val trimmed = note.trim()
        val text = if (trimmed.isEmpty()) "#${type.keyword}" else "#${type.keyword} $trimmed"
        postHabitLine(text)
    }

    /**
     * Records body weight as `#weight weight=<x.x>kg` through the same
     * non-idempotent text endpoint. Weight uses its own habit (separate from
     * the sync's `health-metrics`), so each entry is preserved. Refreshes the
     * last-weight display on success.
     */
    fun trackWeight(kg: Double) {
        val text = "#${ActivityType.Weight.keyword} weight=${"%.1f".format(Locale.US, kg)}kg"
        postHabitLine(text) { refreshHealthDataAsync() }
    }

    /**
     * Shared post path for the activity dialog: sends a habit line, gating the
     * dialog buttons via [activitySaving] and surfacing failures in
     * [activityError]. Closes the dialog and runs [onSuccess] when the post
     * succeeds.
     */
    private fun postHabitLine(text: String, onSuccess: () -> Unit = {}) {
        if (_activitySaving.value) return
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
                onSuccess()
            } catch (t: Throwable) {
                _activityError.value = t.message ?: t.javaClass.simpleName
            } finally {
                _activitySaving.value = false
            }
        }
    }
}
