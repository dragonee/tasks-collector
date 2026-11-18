package org.polybrain.tasks.health.ui

import android.widget.NumberPicker
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
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
import androidx.compose.ui.viewinterop.AndroidView
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.PermissionController
import org.polybrain.tasks.health.R
import org.polybrain.tasks.health.data.HabitMetric
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
            // Tapping the section opens the dialog ready to record a new weight.
            HorizontalDivider()
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .clickable { vm.openActivityDialog("weight") }
                    .padding(vertical = 4.dp),
            ) {
                val weightKg = healthData?.weightKg
                if (weightKg != null) {
                    Text(
                        stringResource(R.string.metric_weight_format)
                            .format(weightKg, formatWeightDate(healthData?.recordedAt))
                    )
                } else {
                    Text(stringResource(R.string.metric_weight_none))
                }
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

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun TrackActivityDialog(vm: MainViewModel) {
    val saving by vm.activitySaving.collectAsState()
    val error by vm.activityError.collectAsState()
    val keywords by vm.activityKeywords.collectAsState()
    val initialKeyword by vm.activityInitialKeyword.collectAsState()

    var chosen by remember { mutableStateOf<String?>(null) }
    var note by remember { mutableStateOf("") }
    var inputs by remember { mutableStateOf(mapOf<String, MetricInput>()) }

    // The keyword asked for (weight from the weight row), else the first,
    // once the list is in.
    val selected = keywords.firstOrNull { it.keyword == (chosen ?: initialKeyword) }
        ?: keywords.firstOrNull()
    val metrics = selected?.habit?.metrics.orEmpty()
    val values = metricValues(metrics, inputs)
    // A habit that records something needs it, or the entry says nothing.
    val canConfirm = selected != null && values != null &&
        (metrics.isEmpty() || values.isNotEmpty() || note.isNotBlank())

    fun update(key: String, input: MetricInput) {
        inputs = inputs + (key to input)
    }

    AlertDialog(
        onDismissRequest = { vm.closeActivityDialog() },
        title = { Text(stringResource(R.string.activity_dialog_title)) },
        text = {
            Column(
                modifier = Modifier.verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    keywords.forEach { keyword ->
                        FilterChip(
                            selected = keyword == selected,
                            onClick = {
                                chosen = keyword.keyword
                                inputs = emptyMap()
                            },
                            label = { Text("#${keyword.keyword}") },
                        )
                    }
                }
                metrics.forEach { metric ->
                    MetricField(
                        metric = metric,
                        input = inputs[metric.key] ?: MetricInput(),
                        onChange = { update(metric.key, it) },
                    )
                }
                OutlinedTextField(
                    value = note,
                    onValueChange = { note = it },
                    placeholder = { Text(stringResource(R.string.activity_note_hint)) },
                    singleLine = false,
                    minLines = if (metrics.isEmpty()) 3 else 1,
                    modifier = Modifier.fillMaxWidth(),
                )
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
                    if (selected != null && values != null) {
                        vm.trackActivity(selected.keyword, note, values)
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

/** The field for one metric of the habit, by its kind. */
@Composable
private fun MetricField(metric: HabitMetric, input: MetricInput, onChange: (MetricInput) -> Unit) {
    val label = metric.label.ifBlank { metric.key }
    when (metric.kind) {
        "duration" -> Column {
            Text(label, style = MaterialTheme.typography.bodyMedium)
            Row(
                horizontalArrangement = Arrangement.spacedBy(16.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                DurationWheel(
                    label = stringResource(R.string.running_minutes_label),
                    value = input.first.toIntOrNull() ?: 0,
                    range = 0..600,
                    onValueChange = { onChange(input.copy(first = it.toString())) },
                )
                DurationWheel(
                    label = stringResource(R.string.running_seconds_label),
                    value = input.second.toIntOrNull() ?: 0,
                    range = 0..59,
                    onValueChange = { onChange(input.copy(second = it.toString())) },
                )
            }
        }
        "pressure" -> Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            NumberField(
                value = input.first,
                label = "$label ${stringResource(R.string.metric_upper)}",
                decimal = false,
                onChange = { onChange(input.copy(first = it)) },
                modifier = Modifier.weight(1f),
            )
            NumberField(
                value = input.second,
                label = stringResource(R.string.metric_lower),
                decimal = false,
                onChange = { onChange(input.copy(second = it)) },
                modifier = Modifier.weight(1f),
            )
        }
        "money" -> Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            NumberField(
                value = input.first,
                label = label,
                decimal = true,
                onChange = { onChange(input.copy(first = it)) },
                modifier = Modifier.weight(2f),
            )
            OutlinedTextField(
                value = input.second,
                onValueChange = { onChange(input.copy(second = it.take(3))) },
                placeholder = { Text("PLN") },
                singleLine = true,
                modifier = Modifier.weight(1f),
            )
        }
        else -> NumberField(
            value = input.first,
            label = if (metric.unit.isEmpty()) label else "$label (${metric.unit})",
            decimal = metric.decimals > 0,
            onChange = { onChange(input.copy(first = it)) },
            modifier = Modifier.fillMaxWidth(),
        )
    }
}

@Composable
private fun NumberField(
    value: String,
    label: String,
    decimal: Boolean,
    onChange: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    OutlinedTextField(
        value = value,
        onValueChange = onChange,
        label = { Text(label) },
        singleLine = true,
        keyboardOptions = KeyboardOptions(
            keyboardType = if (decimal) KeyboardType.Decimal else KeyboardType.Number,
        ),
        modifier = modifier,
    )
}

/**
 * A labelled spinning "wheel" for one component of a duration. Compose has
 * no native wheel picker, so this wraps the platform [NumberPicker] View; the
 * label sits above it and [onValueChange] mirrors each scroll back into state.
 */
@Composable
private fun DurationWheel(
    label: String,
    value: Int,
    range: IntRange,
    onValueChange: (Int) -> Unit,
) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(text = label, style = MaterialTheme.typography.bodySmall)
        AndroidView(
            factory = { context ->
                NumberPicker(context).apply {
                    minValue = range.first
                    maxValue = range.last
                    this.value = value
                    setOnValueChangedListener { _, _, newValue -> onValueChange(newValue) }
                }
            },
            update = { picker ->
                picker.minValue = range.first
                picker.maxValue = range.last
                if (picker.value != value) picker.value = value
            },
        )
    }
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
