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
import org.polybrain.tasks.health.data.HabitKeyword
import org.polybrain.tasks.health.data.TrackedHabitRequest
import org.polybrain.tasks.health.location.TripTracker
import org.polybrain.tasks.health.sync.SyncScheduler
import java.time.LocalDate
import java.time.OffsetDateTime
import java.time.ZoneId
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.JsonObject

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

    /** The role whose habit the dialog should preselect when it opens (weight
     *  when it is opened by tapping the weight section); null for the first. */
    private val _activityInitialRole = MutableStateFlow<String?>(null)
    val activityInitialRole: StateFlow<String?> = _activityInitialRole.asStateFlow()

    /** The habits the dialog offers, by keyword, each with what it records.
     *  Empty until [loadActivityKeywords] first succeeds. */
    private val _activityKeywords = MutableStateFlow<List<HabitKeyword>>(emptyList())
    val activityKeywords: StateFlow<List<HabitKeyword>> = _activityKeywords.asStateFlow()

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

    fun openActivityDialog(initialRole: String? = null) {
        _activityInitialRole.value = initialRole
        _activityError.value = null
        _activityDialogOpen.value = true
        loadActivityKeywords()
    }

    fun closeActivityDialog() {
        if (_activitySaving.value) return
        _activityDialogOpen.value = false
    }

    /** Fetch the habits the dialog offers, again each time it opens: their
     *  metrics may have changed on the web. */
    private fun loadActivityKeywords() {
        viewModelScope.launch {
            val snapshot = settings.snapshot()
            if (!snapshot.isConfigured) {
                _activityError.value = "Configure server URL and API token first."
                return@launch
            }
            try {
                _activityKeywords.value =
                    TasksClient.build(snapshot.serverUrl, snapshot.apiToken).listActivityKeywords()
            } catch (t: Throwable) {
                _activityError.value = t.message ?: t.javaClass.simpleName
            }
        }
    }

    /**
     * Records an activity: a new entry of [keyword]'s habit each time (two gym
     * visits a day are two), its note the hashtag and what was written, and
     * [values] of the habit's metrics, which the server writes into the note.
     * Refreshes the last-weight display on success: it may have been a weigh-in.
     */
    fun trackActivity(keyword: String, note: String, values: JsonObject) {
        postActivity(
            TrackedHabitRequest(
                keyword = keyword,
                // Wall-clock moment of the tap, so the entry lands on today.
                published = OffsetDateTime.now().toString(),
                note = activityNote(keyword, note),
                values = values,
            )
        ) { refreshHealthDataAsync() }
    }

    /**
     * Shared post path for the activity dialog: sends the entry, gating the
     * dialog buttons via [activitySaving] and surfacing failures in
     * [activityError]. Closes the dialog and runs [onSuccess] when the post
     * succeeds.
     */
    private fun postActivity(body: TrackedHabitRequest, onSuccess: () -> Unit = {}) {
        if (_activitySaving.value) return
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
                api.trackHabitValues(body)
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
