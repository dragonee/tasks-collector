package org.polybrain.tasks.health.ui

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.PermissionController
import org.polybrain.tasks.health.R
import java.time.Instant
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import kotlinx.coroutines.launch

@Composable
fun HealthScreen(vm: MainViewModel) {
    val state by vm.settingsState.collectAsState()
    val permissionsGranted by vm.permissionsGranted.collectAsState()
    val todayMetrics by vm.todayMetrics.collectAsState()
    val healthData by vm.healthData.collectAsState()
    val activityDialogOpen by vm.activityDialogOpen.collectAsState()
    val scope = rememberCoroutineScope()

    val permissionLauncher = rememberLauncherForActivityResult(
        contract = PermissionController.createRequestPermissionResultContract(),
    ) {
        scope.launch { vm.refreshPermissionState() }
    }

    Box(modifier = Modifier.fillMaxSize()) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                // Bottom padding clears the FAB so the last row stays tappable.
                .padding(start = 24.dp, top = 24.dp, end = 24.dp, bottom = 96.dp),
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

            // Last recorded weight comes from the server (independent of Health
            // Connect permissions), so it shows regardless of the grant state.
            HorizontalDivider()
            val weightKg = healthData?.weightKg
            if (weightKg != null) {
                Text(
                    stringResource(R.string.metric_weight_format)
                        .format(weightKg, formatWeightDate(healthData?.recordedAt))
                )
            } else {
                Text(stringResource(R.string.metric_weight_none))
            }

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

        FloatingActionButton(
            onClick = { vm.openActivityDialog() },
            modifier = Modifier
                .align(Alignment.BottomEnd)
                .padding(24.dp),
        ) {
            Icon(
                imageVector = Icons.Filled.Add,
                contentDescription = stringResource(R.string.activity_fab_label),
            )
        }
    }

    if (activityDialogOpen) {
        TrackActivityDialog(vm)
    }
}

@Composable
private fun TrackActivityDialog(vm: MainViewModel) {
    val saving by vm.activitySaving.collectAsState()
    val error by vm.activityError.collectAsState()

    var selectedType by remember { mutableStateOf(ActivityType.Gym) }
    var note by remember { mutableStateOf("") }
    var weightText by remember { mutableStateOf("") }

    val isWeight = selectedType == ActivityType.Weight
    val weightKg = weightText.trim().toDoubleOrNull()
    val canConfirm = if (isWeight) weightKg != null && weightKg > 0 else true

    AlertDialog(
        onDismissRequest = { vm.closeActivityDialog() },
        title = { Text(stringResource(R.string.activity_dialog_title)) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    ActivityType.entries.forEach { type ->
                        FilterChip(
                            selected = type == selectedType,
                            onClick = { selectedType = type },
                            label = { Text("#${type.keyword}") },
                        )
                    }
                }
                if (isWeight) {
                    OutlinedTextField(
                        value = weightText,
                        onValueChange = { weightText = it },
                        placeholder = { Text(stringResource(R.string.weight_kg_hint)) },
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                        modifier = Modifier.fillMaxWidth(),
                    )
                } else {
                    OutlinedTextField(
                        value = note,
                        onValueChange = { note = it },
                        placeholder = { Text(stringResource(R.string.activity_note_hint)) },
                        singleLine = false,
                        minLines = 3,
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
                error?.let {
                    Text(
                        text = it,
                        color = MaterialTheme.colorScheme.error,
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
            }
        },
        confirmButton = {
            TextButton(
                onClick = {
                    if (isWeight) {
                        weightKg?.let { vm.trackWeight(it) }
                    } else {
                        vm.trackActivity(selectedType, note)
                    }
                },
                enabled = !saving && canConfirm,
            ) {
                Text(stringResource(R.string.activity_send))
            }
        },
        dismissButton = {
            TextButton(
                onClick = { vm.closeActivityDialog() },
                enabled = !saving,
            ) {
                Text(stringResource(R.string.activity_cancel))
            }
        },
    )
}

private val displayFormatter: DateTimeFormatter =
    DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm")

private val dateFormatter: DateTimeFormatter =
    DateTimeFormatter.ofPattern("yyyy-MM-dd")

private fun formatInstant(epochMs: Long): String =
    Instant.ofEpochMilli(epochMs)
        .atZone(ZoneId.systemDefault())
        .format(displayFormatter)

/** Formats the server's ISO 8601 `recorded_at` as a local date, or "" if absent/unparseable. */
private fun formatWeightDate(iso: String?): String {
    if (iso == null) return ""
    return runCatching {
        OffsetDateTime.parse(iso)
            .atZoneSameInstant(ZoneId.systemDefault())
            .format(dateFormatter)
    }.getOrDefault("")
}
