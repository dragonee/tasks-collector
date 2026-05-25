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
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
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
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import org.polybrain.tasks.health.R
import org.polybrain.tasks.health.data.TripEvent

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
                        EventRow(event)
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
            text = stringResource(R.string.trip_detail_started).format(startedIso),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        if (stoppedIso != null) {
            Text(
                text = stringResource(R.string.trip_detail_stopped).format(stoppedIso),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun EventRow(event: TripEvent) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .background(MaterialTheme.colorScheme.surfaceVariant)
            .padding(12.dp),
    ) {
        Text(
            text = event.published,
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        when (event.type) {
            "journal" -> Text(
                text = event.comment.orEmpty(),
                style = MaterialTheme.typography.bodyMedium,
            )
            "habit" -> Text(
                text = (event.habitName ?: event.habitSlug.orEmpty()) +
                        (event.note?.takeIf { it.isNotBlank() }?.let { " — $it" }
                            ?: ""),
                style = MaterialTheme.typography.bodyMedium,
            )
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
