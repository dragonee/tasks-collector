package org.polybrain.tasks.health.ui.trip

import android.Manifest
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Checkbox
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

@Composable
fun AddNoteDialog(vm: TripDetailViewModel) {
    val gps by vm.gps.collectAsState()
    val allowNoLocation by vm.allowNoLocation.collectAsState()

    var draft by remember { mutableStateOf("") }

    val permissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { granted -> vm.onLocationPermissionResult(granted) }

    val canSend = gps is TripDetailViewModel.GpsState.Ready ||
            (allowNoLocation && gps !is TripDetailViewModel.GpsState.Waiting)

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
                if (gps is TripDetailViewModel.GpsState.Denied ||
                    gps is TripDetailViewModel.GpsState.Unavailable
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(
                            checked = allowNoLocation,
                            onCheckedChange = vm::setAllowNoLocation,
                        )
                        Text(stringResource(R.string.trip_note_send_without_location))
                    }
                }
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
        confirmButton = {
            TextButton(
                onClick = { vm.sendNote(draft) },
                enabled = canSend,
            ) {
                Text(stringResource(R.string.trip_note_send))
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
private fun GpsStatusBlock(
    state: TripDetailViewModel.GpsState,
    onRequestPermission: () -> Unit,
) {
    when (state) {
        TripDetailViewModel.GpsState.Idle,
        TripDetailViewModel.GpsState.Waiting -> Text(
            text = stringResource(R.string.trip_note_gps_waiting),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        is TripDetailViewModel.GpsState.Ready -> Text(
            text = stringResource(R.string.trip_note_gps_ready).format(
                state.fix.lat, state.fix.lng,
            ),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        TripDetailViewModel.GpsState.Denied -> Column {
            Text(
                text = stringResource(R.string.trip_note_gps_missing),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.error,
            )
            TextButton(onClick = onRequestPermission) {
                Text(stringResource(R.string.trip_note_grant_location))
            }
        }
        TripDetailViewModel.GpsState.Unavailable -> Text(
            text = stringResource(R.string.trip_note_gps_missing),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.error,
        )
    }
}
