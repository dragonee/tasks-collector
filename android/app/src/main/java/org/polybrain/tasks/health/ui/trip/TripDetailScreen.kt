package org.polybrain.tasks.health.ui.trip

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale
import org.polybrain.tasks.health.R
import org.polybrain.tasks.health.data.TripEvent

// Fallback only used during the brief window where events have loaded
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
    val events by vm.events.collectAsState()
    val loading by vm.loading.collectAsState()
    val error by vm.error.collectAsState()
    val noteOpen by vm.noteDialogOpen.collectAsState()
    val renameOpen by vm.renameOpen.collectAsState()

    LaunchedEffect(storyId) { vm.load(storyId) }

    val s = story
    // Pick "HH:mm" vs "yyyy-MM-dd HH:mm" once for this render, based on
    // whether the trip spans multiple local calendar dates.
    val formatter: DateTimeFormatter? = s?.let {
        pickEventFormatter(
            startedIso = it.started,
            stoppedIso = it.stopped,
            eventIsos = events.map { e -> e.published },
        )
    }

    Column(modifier = Modifier.fillMaxSize().padding(16.dp)) {
        if (s != null && formatter != null) {
            TripHeader(
                title = s.title,
                startedIso = s.started,
                stoppedIso = s.stopped,
                formatter = formatter,
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
            if (s != null && s.stopped == null) {
                OutlinedButton(onClick = vm::stop) {
                    Text(stringResource(R.string.trip_detail_stop))
                }
            }
        }

        PullToRefreshBox(
            isRefreshing = loading,
            onRefresh = vm::refresh,
            modifier = Modifier.fillMaxSize(),
        ) {
            if (events.isEmpty()) {
                EmptyState(stringResource(R.string.trip_detail_empty))
            } else {
                LazyColumn(
                    modifier = Modifier.fillMaxSize(),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    items(items = events, key = { "${it.type}-${it.id}" }) { event ->
                        EventRow(event, formatter ?: FALLBACK_FORMATTER)
                    }
                }
            }
        }
    }

    if (noteOpen) {
        AddNoteDialog(vm)
    }
    if (renameOpen && s != null) {
        RenameDialog(
            currentTitle = s.title,
            onConfirm = vm::rename,
            onCancel = vm::closeRename,
        )
    }
}

@Composable
private fun TripHeader(
    title: String,
    startedIso: String,
    stoppedIso: String?,
    formatter: DateTimeFormatter,
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
            text = stringResource(R.string.trip_detail_started)
                .format(formatInstant(startedIso, formatter)),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        if (stoppedIso != null) {
            Text(
                text = stringResource(R.string.trip_detail_stopped)
                    .format(formatInstant(stoppedIso, formatter)),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun EventRow(event: TripEvent, formatter: DateTimeFormatter) {
    val context = LocalContext.current
    val parsed = remember(event.id, event.comment) {
        // Only journal events flow through the parser; other types
        // (none today, but the API leaves room for them) just show their
        // type tag.
        if (event.type == "journal") parseTripNote(event.comment.orEmpty())
        else null
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
            else -> Text(
                text = event.type,
                style = MaterialTheme.typography.bodyMedium,
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
