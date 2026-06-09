package org.polybrain.tasks.health.ui.trip

import android.Manifest
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import org.polybrain.tasks.health.R
import org.polybrain.tasks.health.location.GpsState

@Composable
fun AddNoteDialog(vm: TripDetailViewModel) {
    val gps by vm.gps.collectAsState()

    var draft by remember { mutableStateOf("") }

    val permissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { granted -> vm.onLocationPermissionResult(granted) }

    AlertDialog(
        onDismissRequest = { vm.closeAddNote() },
        title = { Text(stringResource(R.string.trip_note_dialog_title)) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                GpsStatusBlock(
                    state = gps,
                    onRequestPermission = {
                        permissionLauncher.launch(Manifest.permission.ACCESS_FINE_LOCATION)
                    },
                )
                OutlinedTextField(
                    value = draft,
                    onValueChange = { draft = it },
                    placeholder = { Text(stringResource(R.string.trip_note_hint)) },
                    singleLine = false,
                    minLines = 3,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        },
        // "Send" is the default action and attaches no location; "Save with
        // location" is the explicit opt-in, enabled only when a fix is ready.
        confirmButton = {
            Row(
                horizontalArrangement = Arrangement.spacedBy(4.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                TextButton(
                    onClick = { vm.sendNote(draft, includeLocation = true) },
                    enabled = gps is GpsState.Ready,
                ) {
                    Text(stringResource(R.string.trip_save_with_location))
                }
                TextButton(
                    onClick = { vm.sendNote(draft, includeLocation = false) },
                    enabled = draft.isNotBlank(),
                ) {
                    Text(stringResource(R.string.trip_send))
                }
            }
        },
        dismissButton = {
            TextButton(onClick = { vm.closeAddNote() }) {
                Text(stringResource(R.string.trip_note_cancel))
            }
        },
    )
}

@Composable
internal fun GpsStatusBlock(
    state: GpsState,
    onRequestPermission: () -> Unit,
) {
    when (state) {
        GpsState.Idle,
        GpsState.Waiting -> Text(
            text = stringResource(R.string.trip_note_gps_waiting),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        is GpsState.Ready -> Text(
            text = stringResource(R.string.trip_note_gps_ready).format(
                state.fix.lat, state.fix.lng,
            ),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        GpsState.Denied -> Column {
            Text(
                text = stringResource(R.string.trip_note_gps_missing),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.error,
            )
            TextButton(onClick = onRequestPermission) {
                Text(stringResource(R.string.trip_note_grant_location))
            }
        }
        GpsState.Unavailable -> Text(
            text = stringResource(R.string.trip_note_gps_missing),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.error,
        )
    }
}
