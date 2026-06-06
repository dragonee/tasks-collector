package org.polybrain.tasks.health.ui.trip

import android.Manifest
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
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
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale
import org.polybrain.tasks.health.R

@Composable
fun AddPhotoDialog(vm: TripDetailViewModel) {
    val gps by vm.gps.collectAsState()
    val selectedPhoto by vm.selectedPhoto.collectAsState()

    var draft by remember { mutableStateOf("") }

    val permissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { granted -> vm.onLocationPermissionResult(granted) }

    AlertDialog(
        onDismissRequest = { vm.closeAddPhoto() },
        title = { Text(stringResource(R.string.trip_photo_dialog_title)) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                selectedPhoto?.let { uri ->
                    AsyncImage(
                        model = uri,
                        contentDescription = null,
                        contentScale = ContentScale.Crop,
                        modifier = Modifier
                            .fillMaxWidth()
                            .aspectRatio(4f / 3f),
                    )
                }
                val gpsState = gps
                if (gpsState is TripDetailViewModel.GpsState.Ready &&
                    gpsState.source == TripDetailViewModel.GpsSource.TRACK
                ) {
                    // A photo's location comes from the recorded trip track, not
                    // a live fix — say so, with the capture time it was matched to.
                    Text(
                        text = stringResource(
                            R.string.trip_note_gps_from_track,
                            formatTrackTime(gpsState.atMillis),
                        ),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                } else {
                    GpsStatusBlock(
                        state = gps,
                        onRequestPermission = {
                            permissionLauncher.launch(Manifest.permission.ACCESS_FINE_LOCATION)
                        },
                    )
                }
                OutlinedTextField(
                    value = draft,
                    onValueChange = { draft = it },
                    placeholder = { Text(stringResource(R.string.trip_photo_hint)) },
                    singleLine = false,
                    minLines = 2,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        },
        // "Send" is the default and attaches no location; "Save with location"
        // is the explicit opt-in, enabled only when the track produced a fix.
        confirmButton = {
            Row(
                horizontalArrangement = Arrangement.spacedBy(4.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                TextButton(
                    onClick = { vm.sendPhoto(draft, includeLocation = true) },
                    enabled = gps is TripDetailViewModel.GpsState.Ready,
                ) {
                    Text(stringResource(R.string.trip_save_with_location))
                }
                TextButton(onClick = { vm.sendPhoto(draft, includeLocation = false) }) {
                    Text(stringResource(R.string.trip_send))
                }
            }
        },
        dismissButton = {
            TextButton(onClick = { vm.closeAddPhoto() }) {
                Text(stringResource(R.string.trip_note_cancel))
            }
        },
    )
}

private val TRACK_TIME_FORMAT: DateTimeFormatter =
    DateTimeFormatter.ofPattern("HH:mm", Locale.US).withZone(ZoneId.systemDefault())

private fun formatTrackTime(millis: Long?): String =
    if (millis == null) "" else TRACK_TIME_FORMAT.format(Instant.ofEpochMilli(millis))
