package org.polybrain.tasks.health.ui

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.PermissionController
import org.polybrain.tasks.health.R
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import kotlinx.coroutines.launch

@Composable
fun HealthScreen(vm: MainViewModel) {
    val state by vm.settingsState.collectAsState()
    val permissionsGranted by vm.permissionsGranted.collectAsState()
    val todayMetrics by vm.todayMetrics.collectAsState()
    val scope = rememberCoroutineScope()

    val permissionLauncher = rememberLauncherForActivityResult(
        contract = PermissionController.createRequestPermissionResultContract(),
    ) {
        scope.launch { vm.refreshPermissionState() }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        when (vm.healthConnectStatus) {
            HealthConnectClient.SDK_UNAVAILABLE -> {
                Text(stringResource(R.string.hc_unavailable))
            }
            HealthConnectClient.SDK_UNAVAILABLE_PROVIDER_UPDATE_REQUIRED -> {
                Text(stringResource(R.string.hc_needs_update))
            }
            else -> {
                if (!permissionsGranted) {
                    Button(onClick = { permissionLauncher.launch(vm.requiredPermissions) }) {
                        Text(stringResource(R.string.grant_permissions))
                    }
                }
            }
        }

        Button(
            onClick = { vm.syncNow() },
            enabled = state.isConfigured && permissionsGranted,
        ) {
            Text(stringResource(R.string.sync_now))
        }

        Text(
            text = when {
                state.lastSyncError.isNotEmpty() ->
                    stringResource(R.string.sync_failed_format).format(state.lastSyncError)
                state.lastSyncEpochMs == 0L ->
                    stringResource(R.string.last_sync_never)
                else ->
                    stringResource(R.string.last_sync_format).format(formatInstant(state.lastSyncEpochMs))
            },
        )

        if (permissionsGranted) {
            HorizontalDivider()
            Text(
                text = stringResource(R.string.today_metrics_heading),
                style = MaterialTheme.typography.titleMedium,
            )
            val metrics = todayMetrics
            if (metrics == null) {
                Text(stringResource(R.string.metric_loading))
            } else {
                Text(stringResource(R.string.metric_steps_format).format(metrics.steps))
                Text(
                    stringResource(R.string.metric_distance_format)
                        .format(metrics.distanceMeters / 1000.0)
                )
                Text(stringResource(R.string.metric_active_format).format(metrics.activeMinutes))
                Text(stringResource(R.string.metric_kcal_format).format(metrics.kcal))
            }
        }
    }
}

private val displayFormatter: DateTimeFormatter =
    DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm")

private fun formatInstant(epochMs: Long): String =
    Instant.ofEpochMilli(epochMs)
        .atZone(ZoneId.systemDefault())
        .format(displayFormatter)
