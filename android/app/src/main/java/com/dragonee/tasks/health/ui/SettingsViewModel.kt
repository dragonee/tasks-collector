package com.dragonee.tasks.health.ui

import android.app.Application
import androidx.health.connect.client.HealthConnectClient
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.dragonee.tasks.health.data.DailyMetrics
import com.dragonee.tasks.health.data.HealthRepository
import com.dragonee.tasks.health.data.Settings
import com.dragonee.tasks.health.data.SettingsSnapshot
import com.dragonee.tasks.health.sync.SyncScheduler
import java.time.LocalDate
import java.time.ZoneId
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

data class UiState(
    val settings: SettingsSnapshot = SettingsSnapshot("", "", 0L, ""),
    val healthConnectStatus: Int = HealthConnectClient.SDK_UNAVAILABLE,
    val permissionsGranted: Boolean = false,
)

class SettingsViewModel(application: Application) : AndroidViewModel(application) {

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

    val healthConnectStatus: Int = health.availability()
    val requiredPermissions: Set<String> = health.permissions

    init {
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
}
