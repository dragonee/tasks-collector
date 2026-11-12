package org.polybrain.tasks.health.ui

import android.app.Application
import android.os.Build
import androidx.health.connect.client.HealthConnectClient
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import org.polybrain.tasks.health.data.DailyMetrics
import org.polybrain.tasks.health.data.HealthDataResponse
import org.polybrain.tasks.health.data.HealthRepository
import org.polybrain.tasks.health.data.OAuthLogin
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
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * The activities the FAB on the Health screen can register, each mapped to the
 * hashtag the backend parses into a [HabitTracked]. [Gym] is the default
 * subtype. The keyword is sent verbatim (Unicode is fine) prefixed with '#'.
 *
 * [Weight] is special: instead of a free-text note it carries a numeric
 * kilogram value, posted as `#weight weight=<x.x>kg` (see [MainViewModel.trackWeight]).
 *
 * [Running] is likewise special: it carries a distance and a duration, posted
 * as `#running distance=<x.x>km, time=<m>m<s>s` (see [MainViewModel.trackRunning]).
 */
enum class ActivityType(val keyword: String) {
    Gym("siłka"),
    Workout("workout"),
    Running("running"),
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

    /** Activity type the dialog should preselect when it opens (e.g. Weight when
     *  the dialog is opened by tapping the weight section). */
    private val _activityInitialType = MutableStateFlow(ActivityType.Gym)
    val activityInitialType: StateFlow<ActivityType> = _activityInitialType.asStateFlow()

    /** True while an activity is being posted; gates the dialog buttons. */
    private val _activitySaving = MutableStateFlow(false)
    val activitySaving: StateFlow<Boolean> = _activitySaving.asStateFlow()

    /** Last activity-post error, shown inline in the dialog (null = none). */
    private val _activityError = MutableStateFlow<String?>(null)
    val activityError: StateFlow<String?> = _activityError.asStateFlow()

    /** True while a login or a logout is being settled with the server. */
    private val _loginBusy = MutableStateFlow(false)
    val loginBusy: StateFlow<Boolean> = _loginBusy.asStateFlow()

    /** Why the last login or logout didn't work (null = it did, or none yet). */
    private val _loginError = MutableStateFlow<String?>(null)
    val loginError: StateFlow<String?> = _loginError.asStateFlow()

    /** Where the server sends the browser back to: this build of the app. */
    private val redirectUri = OAuthLogin.redirectUri(application.packageName)

    val healthConnectStatus: Int = health.availability()
    val requiredPermissions: Set<String> = health.permissions

    init {
        // Resume any trip notes/photos queued offline in a previous session.
        // The worker no-ops when unconfigured, so this is safe to call always.
        SyncScheduler.drainOutbox(application)
        // A phone logged in before plans were kept gets the job here; the
        // job does nothing while logged out.
        SyncScheduler.schedulePlansRefresh(application)
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

    /**
     * Start logging in to [serverUrl] (see [OAuthLogin]): hand [open] the
     * page for the browser to show. The rest happens there, until the
     * browser comes back with an answer for [finishLogin].
     */
    fun startLogin(serverUrl: String, open: (String) -> Unit) {
        viewModelScope.launch {
            val pending = OAuthLogin.start(serverUrl)
            val url = OAuthLogin.authorizeUrl(pending, redirectUri, deviceName())
            if (url == null) {
                _loginError.value = "That is not a server URL."
                return@launch
            }
            _loginError.value = null
            settings.savePendingLogin(pending)
            try {
                open(url)
            } catch (t: Throwable) {
                // No browser to open it with.
                _loginError.value = t.message ?: t.javaClass.simpleName
            }
        }
    }

    /**
     * The browser came back: trade the code for a token and keep it, with
     * the server it is for. [code], [state] and [error] are the parameters
     * of the redirect.
     */
    fun finishLogin(code: String?, state: String?, error: String?) {
        viewModelScope.launch {
            val pending = settings.pendingLogin()
            val answer = OAuthLogin.codeFrom(pending, code, state, error)
            // An answer to this login ends it, whatever the answer is; one
            // to some other login leaves it waiting for its own.
            if (pending != null && state == pending.state) settings.clearPendingLogin()
            if (pending == null || answer !is OAuthLogin.Answer.Code) {
                _loginError.value = (answer as? OAuthLogin.Answer.Refused)?.reason
                return@launch
            }
            _loginBusy.value = true
            try {
                val token = withContext(Dispatchers.IO) {
                    TasksClient.exchangeCode(pending, answer.code, redirectUri)
                }
                settings.saveServerConfig(pending.serverUrl, token)
                _loginError.value = null
                SyncScheduler.schedule(getApplication())
                // What was queued while logged out can go now.
                SyncScheduler.drainOutbox(getApplication())
                refreshHealthData()
            } catch (t: Throwable) {
                _loginError.value = t.message ?: t.javaClass.simpleName
            } finally {
                _loginBusy.value = false
            }
        }
    }

    /**
     * Log out: have the server forget this phone's token, then forget it
     * here. When the server can't be told the token is kept, so that it
     * isn't left working with nobody holding it; it can always be revoked
     * in the account settings on the web.
     */
    fun logout() {
        viewModelScope.launch {
            val snapshot = settings.snapshot()
            if (!snapshot.isConfigured) return@launch
            _loginBusy.value = true
            try {
                withContext(Dispatchers.IO) {
                    TasksClient.revokeToken(snapshot.serverUrl, snapshot.apiToken)
                }
                settings.saveServerConfig(snapshot.serverUrl, "")
                _loginError.value = null
            } catch (t: Throwable) {
                _loginError.value = t.message ?: t.javaClass.simpleName
            } finally {
                _loginBusy.value = false
            }
        }
    }

    /** What the user will know this phone by in their account settings. */
    private fun deviceName(): String {
        val model = Build.MODEL.orEmpty()
        val maker = Build.MANUFACTURER.orEmpty().replaceFirstChar { it.uppercase() }
        return if (model.startsWith(maker, ignoreCase = true)) model else "$maker $model".trim()
    }

    fun syncNow() {
        SyncScheduler.runOnce(getApplication())
        refreshMetricsAsync()
        refreshHealthDataAsync()
    }

    fun openActivityDialog(initialType: ActivityType = ActivityType.Gym) {
        _activityInitialType.value = initialType
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
     * Records a run as `#running distance=<x.x>km, time=<m>m<s>s` through the
     * same non-idempotent text endpoint. Distance is formatted with one decimal
     * (US locale, so the separator is a dot the backend can parse).
     */
    fun trackRunning(distanceKm: Double, minutes: Int, seconds: Int) {
        val distance = "%.1f".format(Locale.US, distanceKm)
        val text = "#${ActivityType.Running.keyword} distance=${distance}km, time=${minutes}m${seconds}s"
        postHabitLine(text)
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
