package org.polybrain.tasks.health.ui.trip

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.DatePicker
import androidx.compose.material3.DatePickerDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.SelectableDates
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TimePicker
import androidx.compose.material3.rememberDatePickerState
import androidx.compose.material3.rememberTimePickerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.DialogProperties
import java.time.Instant
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.LocalTime
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import java.util.Locale
import org.polybrain.tasks.health.R

private val STOP_AT_FORMAT: DateTimeFormatter =
    DateTimeFormatter.ofPattern("EEE, d MMM yyyy HH:mm", Locale.getDefault())

/**
 * Picks the moment a trip ended, so a trip you forgot to stop can be closed at
 * the time you actually got home rather than whenever you next opened the app.
 *
 * Opens on the current date and time, so confirming straight away is the plain
 * "stop it now" case. Date and time are edited one at a time, each in its own
 * picker dialog stacked over this one.
 *
 * [startedIso] bounds the choice: the calendar greys out days outside the
 * trip's lifetime and Confirm stays disabled while the composed instant falls
 * outside `started..now`. The server enforces the same window.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun StopTripDialog(
    startedIso: String,
    onConfirm: (OffsetDateTime) -> Unit,
    onDismiss: () -> Unit,
) {
    val zone = remember { ZoneId.systemDefault() }
    val started = remember(startedIso) {
        OffsetDateTime.parse(startedIso).atZoneSameInstant(zone).toLocalDateTime()
    }
    val now = remember { LocalDateTime.now(zone).withSecond(0).withNano(0) }

    var chosen by remember { mutableStateOf(now) }
    var editing by remember { mutableStateOf(Editing.NONE) }

    val valid = !chosen.isBefore(started) && !chosen.isAfter(now)

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(stringResource(R.string.trip_stop_dialog_title)) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(
                    text = stringResource(R.string.trip_stop_hint),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Text(
                    text = STOP_AT_FORMAT.format(chosen),
                    style = MaterialTheme.typography.titleMedium,
                )
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    TextButton(onClick = { editing = Editing.DATE }) {
                        Text(stringResource(R.string.trip_stop_change_date))
                    }
                    TextButton(onClick = { editing = Editing.TIME }) {
                        Text(stringResource(R.string.trip_stop_change_time))
                    }
                }
                if (!valid) {
                    Text(
                        text = stringResource(R.string.trip_stop_out_of_range),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.error,
                    )
                }
            }
        },
        confirmButton = {
            TextButton(
                onClick = { onConfirm(chosen.atZone(zone).toOffsetDateTime()) },
                enabled = valid,
            ) {
                Text(stringResource(R.string.trip_detail_stop))
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text(stringResource(R.string.trip_note_cancel))
            }
        },
    )

    when (editing) {
        Editing.NONE -> Unit
        Editing.DATE -> StopDatePickerDialog(
            date = chosen,
            earliest = started,
            latest = now,
            onPicked = { picked ->
                chosen = LocalDateTime.of(picked, chosen.toLocalTime())
                editing = Editing.NONE
            },
            onDismiss = { editing = Editing.NONE },
        )
        Editing.TIME -> StopTimePickerDialog(
            time = chosen.toLocalTime(),
            onPicked = { picked ->
                chosen = LocalDateTime.of(chosen.toLocalDate(), picked)
                editing = Editing.NONE
            },
            onDismiss = { editing = Editing.NONE },
        )
    }
}

/** Which sub-picker is stacked over the dialog (NONE = just the summary). */
private enum class Editing { NONE, DATE, TIME }

/**
 * The calendar. `DatePickerState` works in UTC milliseconds-since-epoch and
 * means them as plain calendar days, so every conversion in here pins
 * [ZoneOffset.UTC] — reading them back in the device zone would shift the
 * selection by a day either side of midnight.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun StopDatePickerDialog(
    date: LocalDateTime,
    earliest: LocalDateTime,
    latest: LocalDateTime,
    onPicked: (LocalDate) -> Unit,
    onDismiss: () -> Unit,
) {
    val state = rememberDatePickerState(
        initialSelectedDateMillis = date.toLocalDate()
            .atStartOfDay(ZoneOffset.UTC)
            .toInstant()
            .toEpochMilli(),
        selectableDates = remember(earliest, latest) {
            object : SelectableDates {
                override fun isSelectableDate(utcTimeMillis: Long): Boolean {
                    val day = Instant.ofEpochMilli(utcTimeMillis)
                        .atZone(ZoneOffset.UTC)
                        .toLocalDate()
                    return !day.isBefore(earliest.toLocalDate()) &&
                        !day.isAfter(latest.toLocalDate())
                }
            }
        },
    )

    DatePickerDialog(
        onDismissRequest = onDismiss,
        confirmButton = {
            TextButton(
                onClick = {
                    state.selectedDateMillis?.let { millis ->
                        onPicked(
                            Instant.ofEpochMilli(millis).atZone(ZoneOffset.UTC).toLocalDate()
                        )
                    }
                },
                enabled = state.selectedDateMillis != null,
            ) {
                Text(stringResource(R.string.trip_stop_set))
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text(stringResource(R.string.trip_note_cancel))
            }
        },
    ) {
        DatePicker(state = state)
    }
}

/** The clock. 24-hour, like every other time this app prints. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun StopTimePickerDialog(
    time: LocalTime,
    onPicked: (LocalTime) -> Unit,
    onDismiss: () -> Unit,
) {
    val state = rememberTimePickerState(
        initialHour = time.hour,
        initialMinute = time.minute,
        is24Hour = true,
    )

    AlertDialog(
        onDismissRequest = onDismiss,
        // The clock dial is wider than a dialog's platform default width and
        // would be clipped; let this one size itself to its content instead.
        properties = DialogProperties(usePlatformDefaultWidth = false),
        title = { Text(stringResource(R.string.trip_stop_time_title)) },
        text = { TimePicker(state = state) },
        confirmButton = {
            TextButton(onClick = { onPicked(LocalTime.of(state.hour, state.minute)) }) {
                Text(stringResource(R.string.trip_stop_set))
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text(stringResource(R.string.trip_note_cancel))
            }
        },
    )
}
