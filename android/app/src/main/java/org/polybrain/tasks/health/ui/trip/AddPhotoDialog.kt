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
import androidx.compose.material3.Checkbox
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
import org.polybrain.tasks.health.R

@Composable
fun AddPhotoDialog(vm: TripDetailViewModel) {
    val gps by vm.gps.collectAsState()
    val allowNoLocation by vm.allowNoLocation.collectAsState()
    val selectedPhoto by vm.selectedPhoto.collectAsState()

    var draft by remember { mutableStateOf("") }

    val permissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { granted -> vm.onLocationPermissionResult(granted) }

    // Sending now just queues the photo to the outbox and closes the dialog —
    // the upload happens in the background, so there's no in-dialog spinner.
    val canSend = gps is TripDetailViewModel.GpsState.Ready ||
        (allowNoLocation && gps !is TripDetailViewModel.GpsState.Waiting)

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
                    placeholder = { Text(stringResource(R.string.trip_photo_hint)) },
                    singleLine = false,
                    minLines = 2,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        },
        confirmButton = {
            TextButton(
                onClick = { vm.sendPhoto(draft) },
                enabled = canSend,
            ) {
                Text(stringResource(R.string.trip_photo_send))
            }
        },
        dismissButton = {
            TextButton(onClick = { vm.closeAddPhoto() }) {
                Text(stringResource(R.string.trip_note_cancel))
            }
        },
    )
}
