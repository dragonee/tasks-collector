package org.polybrain.tasks.health.ui

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.PermissionController
import androidx.lifecycle.viewmodel.compose.viewModel
import org.polybrain.tasks.health.R
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import kotlinx.coroutines.launch

@Composable
fun SettingsScreen(vm: SettingsViewModel = viewModel()) {
    val state by vm.settingsState.collectAsState()
    val permissionsGranted by vm.permissionsGranted.collectAsState()
    val todayMetrics by vm.todayMetrics.collectAsState()
    val scope = rememberCoroutineScope()

    var url by remember { mutableStateOf("") }
    var token by remember { mutableStateOf("") }
    LaunchedEffect(state.serverUrl, state.apiToken) {
        if (url.isEmpty()) url = state.serverUrl
        if (token.isEmpty()) token = state.apiToken
    }

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
        OutlinedTextField(
            value = url,
            onValueChange = { url = it },
            label = { Text(stringRes(R.string.server_url_label)) },
            placeholder = { Text(stringRes(R.string.server_url_placeholder)) },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )

        OutlinedTextField(
            value = token,
            onValueChange = { token = it },
            label = { Text(stringRes(R.string.api_token_label)) },
            singleLine = true,
            visualTransformation = PasswordVisualTransformation(),
            modifier = Modifier.fillMaxWidth(),
        )

        Button(
            onClick = { vm.save(url, token) },
            enabled = url.isNotBlank() && token.isNotBlank(),
        ) {
            Text(stringRes(R.string.save))
        }

        when (vm.healthConnectStatus) {
            HealthConnectClient.SDK_UNAVAILABLE -> {
                Text(stringRes(R.string.hc_unavailable))
            }
            HealthConnectClient.SDK_UNAVAILABLE_PROVIDER_UPDATE_REQUIRED -> {
                Text(stringRes(R.string.hc_needs_update))
            }
            else -> {
                if (!permissionsGranted) {
                    Button(onClick = { permissionLauncher.launch(vm.requiredPermissions) }) {
                        Text(stringRes(R.string.grant_permissions))
                    }
                }
            }
        }

        Button(
            onClick = { vm.syncNow() },
            enabled = state.isConfigured && permissionsGranted,
        ) {
            Text(stringRes(R.string.sync_now))
        }

        Text(
            text = when {
                state.lastSyncError.isNotEmpty() ->
                    stringRes(R.string.sync_failed_format).format(state.lastSyncError)
                state.lastSyncEpochMs == 0L ->
                    stringRes(R.string.last_sync_never)
                else ->
                    stringRes(R.string.last_sync_format).format(formatInstant(state.lastSyncEpochMs))
            },
        )

        if (permissionsGranted) {
            HorizontalDivider()
            Text(
                text = stringRes(R.string.today_metrics_heading),
                style = MaterialTheme.typography.titleMedium,
            )
            val metrics = todayMetrics
            if (metrics == null) {
                Text(stringRes(R.string.metric_loading))
            } else {
                Text(stringRes(R.string.metric_steps_format).format(metrics.steps))
                Text(
                    stringRes(R.string.metric_distance_format)
                        .format(metrics.distanceMeters / 1000.0)
                )
                Text(stringRes(R.string.metric_active_format).format(metrics.activeMinutes))
                Text(stringRes(R.string.metric_kcal_format).format(metrics.kcal))
            }
        }
    }
}

@Composable
private fun stringRes(id: Int): String =
    androidx.compose.ui.res.stringResource(id = id)

private val displayFormatter: DateTimeFormatter =
    DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm")

private fun formatInstant(epochMs: Long): String =
    Instant.ofEpochMilli(epochMs)
        .atZone(ZoneId.systemDefault())
        .format(displayFormatter)
