package org.polybrain.tasks.health.ui.trip

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Place
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.lifecycle.viewmodel.compose.viewModel
import coil.compose.AsyncImage
import java.io.File
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale
import org.polybrain.tasks.health.R
import org.polybrain.tasks.health.data.OutboxItem
import org.polybrain.tasks.health.data.TripEvent
import org.polybrain.tasks.health.ui.trip.TripDetailViewModel.TimelineRow

// Fallback only used during the brief window where rows have loaded
// but the story object hasn't yet — pickEventFormatter needs both.
private val FALLBACK_FORMATTER: DateTimeFormatter =
    DateTimeFormatter.ofPattern("HH:mm", Locale.US).withZone(ZoneId.systemDefault())

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TripDetailScreen(
    storyId: Long,
    vm: TripDetailViewModel = viewModel(),
) {
    val story by vm.story.collectAsState()
    val timeline by vm.timeline.collectAsState()
    val pending by vm.pending.collectAsState()
    val syncing by vm.syncing.collectAsState()
    val loading by vm.loading.collectAsState()
    val error by vm.error.collectAsState()
    val noteOpen by vm.noteDialogOpen.collectAsState()
    val photoOpen by vm.photoDialogOpen.collectAsState()
    val renameOpen by vm.renameOpen.collectAsState()
    val viewerUrl by vm.viewerUrl.collectAsState()

    LaunchedEffect(storyId) { vm.load(storyId) }

    val photoPicker = rememberLauncherForActivityResult(
        ActivityResultContracts.PickVisualMedia(),
    ) { uri -> if (uri != null) vm.openAddPhoto(uri) }

    val s = story
    // Pick "HH:mm" vs "yyyy-MM-dd HH:mm" once for this render, based on
    // whether the trip spans multiple local calendar dates.
    val formatter: DateTimeFormatter? = s?.let {
        pickEventFormatter(
            startedIso = it.started,
            stoppedIso = it.stopped,
            eventIsos = timeline.map { row -> row.publishedIso },
        )
    }

    Column(modifier = Modifier.fillMaxSize().padding(16.dp)) {
        if (s != null) {
            TripHeader(
                title = s.title,
                startedIso = s.started,
                stoppedIso = s.stopped,
                onRename = vm::openRename,
            )
        }

        error?.let { ErrorBanner(message = it, onDismiss = vm::clearError) }

        Row(
            modifier = Modifier.fillMaxWidth().padding(vertical = 12.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Button(
                onClick = vm::openAddNote,
                enabled = s != null && s.stopped == null,
                modifier = Modifier.weight(1f),
            ) {
                Text(stringResource(R.string.trip_detail_add_note))
            }
            OutlinedButton(
                onClick = {
                    photoPicker.launch(
                        PickVisualMediaRequest(
                            ActivityResultContracts.PickVisualMedia.ImageOnly
                        )
                    )
                },
                enabled = s != null && s.stopped == null,
            ) {
                Text(stringResource(R.string.trip_detail_add_photo))
            }
            if (s != null && s.stopped == null) {
                OutlinedButton(onClick = vm::stop) {
                    Text(stringResource(R.string.trip_detail_stop))
                }
            }
        }

        SyncBadge(
            pending = pending,
            syncing = syncing,
            onRetryAll = { pending.filter { it.failedPermanently }.forEach(vm::retry) },
        )

        PullToRefreshBox(
            isRefreshing = loading,
            onRefresh = vm::refresh,
            modifier = Modifier.fillMaxSize(),
        ) {
            if (timeline.isEmpty()) {
                EmptyState(stringResource(R.string.trip_detail_empty))
            } else {
                LazyColumn(
                    modifier = Modifier.fillMaxSize(),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    items(items = timeline, key = ::rowKey) { row ->
                        when (row) {
                            is TimelineRow.Synced -> EventRow(
                                event = row.event,
                                formatter = formatter ?: FALLBACK_FORMATTER,
                                onOpenPhoto = vm::openPhoto,
                            )
                            is TimelineRow.Pending -> PendingRow(
                                item = row.item,
                                formatter = formatter ?: FALLBACK_FORMATTER,
                                syncing = syncing,
                                photoFile = vm.pendingPhotoFile(row.item),
                                onRetry = { vm.retry(row.item) },
                                onDiscard = { vm.discard(row.item) },
                            )
                        }
                    }
                }
            }
        }
    }

    if (noteOpen) {
        AddNoteDialog(vm)
    }
    if (photoOpen) {
        AddPhotoDialog(vm)
    }
    if (renameOpen && s != null) {
        RenameDialog(
            currentTitle = s.title,
            onConfirm = vm::rename,
            onCancel = vm::closeRename,
        )
    }
    viewerUrl?.let { url ->
        PhotoViewerDialog(url = url, onDismiss = vm::closeViewer)
    }
}

private fun rowKey(row: TimelineRow): String = when (row) {
    is TimelineRow.Synced -> "s-${row.event.type}-${row.event.id}"
    is TimelineRow.Pending -> "p-${row.item.id}"
}

@Composable
private fun SyncBadge(
    pending: List<OutboxItem>,
    syncing: Boolean,
    onRetryAll: () -> Unit,
) {
    val waiting = pending.count { !it.failedPermanently }
    val failed = pending.count { it.failedPermanently }
    if (waiting == 0 && failed == 0) return

    Column(
        modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        if (waiting > 0) {
            Text(
                text = stringResource(
                    if (syncing) R.string.trip_sync_badge_syncing
                    else R.string.trip_sync_badge_waiting,
                    waiting,
                ),
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        if (failed > 0) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = stringResource(R.string.trip_sync_badge_failed, failed),
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.error,
                    modifier = Modifier.weight(1f),
                )
                TextButton(onClick = onRetryAll) {
                    Text(stringResource(R.string.trip_sync_retry_all))
                }
            }
        }
    }
}

@Composable
private fun PhotoViewerDialog(url: String, onDismiss: () -> Unit) {
    Dialog(onDismissRequest = onDismiss) {
        AsyncImage(
            model = url,
            contentDescription = null,
            contentScale = ContentScale.Fit,
            modifier = Modifier
                .fillMaxWidth()
                .clickable(onClick = onDismiss),
        )
    }
}

@Composable
private fun TripHeader(
    title: String,
    startedIso: String,
    stoppedIso: String?,
    onRename: () -> Unit,
) {
    Column(modifier = Modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = title,
                style = MaterialTheme.typography.titleLarge,
                modifier = Modifier.weight(1f),
            )
            TextButton(onClick = onRename) {
                Text(stringResource(R.string.trip_detail_rename))
            }
        }
        Text(
            text = formatTripRange(startedIso, stoppedIso),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun EventRow(
    event: TripEvent,
    formatter: DateTimeFormatter,
    onOpenPhoto: (Long) -> Unit,
) {
    val context = LocalContext.current
    // Journal and photo events both carry a comment that may start with a
    // #poi line; parse it so the location pin and clean body text show.
    val parsed = remember(event.id, event.comment) {
        if (event.type == "journal" || event.type == "photo") {
            parseTripNote(event.comment.orEmpty())
        } else {
            null
        }
    }

    Column(
        modifier = Modifier
            .fillMaxWidth()
            .background(MaterialTheme.colorScheme.surfaceVariant)
            .padding(12.dp),
    ) {
        Text(
            text = formatInstant(event.published, formatter),
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        when (event.type) {
            "journal" -> {
                val poi = parsed?.poi
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(
                        text = parsed?.text.orEmpty(),
                        style = MaterialTheme.typography.bodyMedium,
                        modifier = Modifier.weight(1f),
                    )
                    if (poi != null) {
                        IconButton(onClick = { openPoiInMaps(context, poi) }) {
                            Icon(
                                imageVector = Icons.Filled.Place,
                                contentDescription = stringResource(
                                    R.string.trip_detail_open_in_maps
                                ),
                            )
                        }
                    }
                }
            }
            "photo" -> PhotoEventBody(event, parsed, onOpenPhoto)
            else -> Text(
                text = event.type,
                style = MaterialTheme.typography.bodyMedium,
            )
        }
    }
}

@Composable
private fun PhotoEventBody(
    event: TripEvent,
    parsed: ParsedTripNote?,
    onOpenPhoto: (Long) -> Unit,
) {
    val context = LocalContext.current
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        val thumb = event.thumbnailUrl
        if (thumb != null) {
            // Right-aligned, full frame visible (no crop).
            AsyncImage(
                model = thumb,
                contentDescription = parsed?.text,
                contentScale = ContentScale.Fit,
                alignment = Alignment.CenterEnd,
                modifier = Modifier
                    .align(Alignment.End)
                    .fillMaxWidth(0.6f)
                    .heightIn(max = 240.dp)
                    .clickable { onOpenPhoto(event.id) },
            )
        } else {
            // Thumbnail not generated yet — pull-to-refresh will fill it.
            Box(
                modifier = Modifier
                    .align(Alignment.End)
                    .fillMaxWidth(0.6f)
                    .heightIn(min = 120.dp)
                    .background(MaterialTheme.colorScheme.surface)
                    .clickable { onOpenPhoto(event.id) },
                contentAlignment = Alignment.Center,
            ) {
                Text(
                    text = stringResource(R.string.trip_photo_processing),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
        val body = parsed?.text.orEmpty()
        val poi = parsed?.poi
        if (body.isNotBlank() || poi != null) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = body,
                    style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier.weight(1f),
                )
                if (poi != null) {
                    IconButton(onClick = { openPoiInMaps(context, poi) }) {
                        Icon(
                            imageVector = Icons.Filled.Place,
                            contentDescription = stringResource(
                                R.string.trip_detail_open_in_maps
                            ),
                        )
                    }
                }
            }
        }
    }
}

/**
 * A queued (not-yet-synced) note or photo. Mirrors [EventRow]'s layout so the
 * timeline reads consistently, but loads the photo from the local outbox file
 * and shows a sync-status line (with retry/discard once it has failed).
 */
@Composable
private fun PendingRow(
    item: OutboxItem,
    formatter: DateTimeFormatter,
    syncing: Boolean,
    photoFile: File?,
    onRetry: () -> Unit,
    onDiscard: () -> Unit,
) {
    val context = LocalContext.current
    val parsed = remember(item.id, item.comment) { parseTripNote(item.comment) }

    Column(
        modifier = Modifier
            .fillMaxWidth()
            .background(MaterialTheme.colorScheme.surfaceVariant)
            .padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Text(
            text = formatInstant(item.published, formatter),
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )

        if (item.isPhoto && photoFile != null) {
            AsyncImage(
                model = photoFile,
                contentDescription = parsed.text,
                contentScale = ContentScale.Fit,
                alignment = Alignment.CenterEnd,
                modifier = Modifier
                    .align(Alignment.End)
                    .fillMaxWidth(0.6f)
                    .heightIn(max = 240.dp),
            )
        }

        val body = parsed.text
        val poi = parsed.poi
        if (body.isNotBlank() || poi != null) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = body,
                    style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier.weight(1f),
                )
                if (poi != null) {
                    IconButton(onClick = { openPoiInMaps(context, poi) }) {
                        Icon(
                            imageVector = Icons.Filled.Place,
                            contentDescription = stringResource(
                                R.string.trip_detail_open_in_maps
                            ),
                        )
                    }
                }
            }
        }

        if (item.failedPermanently) {
            Text(
                text = stringResource(R.string.trip_sync_failed, item.lastError.orEmpty()),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.error,
            )
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                TextButton(onClick = onRetry) {
                    Text(stringResource(R.string.trip_sync_retry))
                }
                TextButton(onClick = onDiscard) {
                    Text(stringResource(R.string.trip_sync_discard))
                }
            }
        } else {
            Text(
                text = stringResource(
                    if (syncing) R.string.trip_sync_uploading
                    else R.string.trip_sync_waiting
                ),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun RenameDialog(
    currentTitle: String,
    onConfirm: (String) -> Unit,
    onCancel: () -> Unit,
) {
    var draft by remember(currentTitle) { mutableStateOf(currentTitle) }
    AlertDialog(
        onDismissRequest = onCancel,
        title = { Text(stringResource(R.string.trip_detail_rename_title)) },
        text = {
            OutlinedTextField(
                value = draft,
                onValueChange = { draft = it },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
        },
        confirmButton = {
            TextButton(onClick = { onConfirm(draft) }) {
                Text(stringResource(R.string.trip_detail_rename))
            }
        },
        dismissButton = {
            TextButton(onClick = onCancel) {
                Text(stringResource(R.string.trip_note_cancel))
            }
        },
    )
}

@Composable
private fun EmptyState(text: String) {
    Box(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(24.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(text)
    }
}

@Composable
private fun ErrorBanner(message: String, onDismiss: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(MaterialTheme.colorScheme.errorContainer)
            .padding(horizontal = 12.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text = message,
            color = MaterialTheme.colorScheme.onErrorContainer,
            modifier = Modifier.weight(1f),
        )
        TextButton(onClick = onDismiss) {
            Text(stringResource(R.string.today_dismiss_error))
        }
    }
}
