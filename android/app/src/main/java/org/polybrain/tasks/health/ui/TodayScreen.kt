package org.polybrain.tasks.health.ui

import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
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
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import org.polybrain.tasks.health.R
import org.polybrain.tasks.health.data.TodayTask

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TodayScreen(
    vm: TodayViewModel = viewModel(),
    onAddFromBoard: (LocalDate) -> Unit = {},
) {
    val tasks by vm.tasks.collectAsState()
    val weekPlan by vm.weekPlan.collectAsState()
    val loading by vm.loading.collectAsState()
    val error by vm.error.collectAsState()
    val configured by vm.configured.collectAsState()
    val pendingComplete by vm.pendingComplete.collectAsState()
    val selectedDate by vm.selectedDate.collectAsState()

    LaunchedEffect(Unit) { vm.refresh() }

    Box(modifier = Modifier.fillMaxSize()) {
        Column(modifier = Modifier.fillMaxSize().padding(16.dp)) {
            DateNavBar(
                selectedDate = selectedDate,
                onPrevious = vm::previousDay,
                onNext = vm::nextDay,
                onToday = vm::goToToday,
            )

            AddTaskRow(onAdd = vm::add, enabled = configured)

            error?.let { ErrorBanner(message = it, onDismiss = vm::clearError) }

            PullToRefreshBox(
                isRefreshing = loading,
                onRefresh = vm::refresh,
                modifier = Modifier.fillMaxSize(),
            ) {
                // This week's plan items that aren't already on today's list.
                // Adding one copies it onto today, after which it drops out here.
                val todayTexts = tasks.map { it.text }.toSet()
                val pendingWeekPlan = weekPlan.filterNot { it in todayTexts }
                when {
                    !configured -> EmptyState(stringResource(R.string.today_not_configured))
                    tasks.isEmpty() && pendingWeekPlan.isEmpty() ->
                        EmptyState(stringResource(R.string.today_empty))
                    // Bottom padding clears the FAB so the last row stays tappable.
                    else -> LazyColumn(
                        modifier = Modifier.fillMaxSize(),
                        contentPadding = PaddingValues(bottom = 88.dp),
                    ) {
                        if (pendingWeekPlan.isNotEmpty()) {
                            item(key = "week-plan-header") {
                                Text(
                                    text = stringResource(R.string.today_week_plan_heading),
                                    style = MaterialTheme.typography.titleSmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                    modifier = Modifier.padding(bottom = 4.dp),
                                )
                            }
                            items(items = pendingWeekPlan, key = { "week:$it" }) { line ->
                                WeekPlanRow(
                                    text = line,
                                    onAddToToday = { vm.addPlanItemToToday(line) },
                                )
                            }
                        }
                        // Divider only when both sections are present, so it
                        // genuinely separates weekly from daily.
                        if (pendingWeekPlan.isNotEmpty() && tasks.isNotEmpty()) {
                            item(key = "week-plan-divider") {
                                HorizontalDivider(modifier = Modifier.padding(vertical = 8.dp))
                            }
                        }
                        items(items = tasks, key = TodayTask::text) { task ->
                            TaskRow(
                                task = task,
                                onToggle = { done -> vm.requestSetDone(task.text, done) },
                                onDelete = { vm.delete(task.text) },
                            )
                        }
                    }
                }
            }
        }

        // FAB opens the board picker for the currently-viewed day. Hidden
        // until configured, matching the disabled add-task row above.
        if (configured) {
            FloatingActionButton(
                onClick = { onAddFromBoard(selectedDate) },
                modifier = Modifier
                    .align(Alignment.BottomEnd)
                    .padding(24.dp),
            ) {
                Icon(
                    imageVector = Icons.Filled.Add,
                    contentDescription = stringResource(R.string.today_board_fab_label),
                )
            }
        }
    }

    pendingComplete?.let { pending ->
        when (pending) {
            is TodayViewModel.PendingComplete.AddNote -> JournalNoteDialog(
                onConfirm = vm::confirmCompletion,
                onCancel = vm::cancelCompletion,
                // Reset the draft each time a new pending request arrives.
                resetKey = pending.text,
            )
            is TodayViewModel.PendingComplete.CompletedAction -> CompletedTaskDialog(
                taskText = pending.text,
                onAddAnother = vm::confirmAddAnother,
                onReset = vm::confirmReset,
                onCancel = vm::cancelCompletion,
                resetKey = pending.text,
            )
        }
    }
}

@Composable
private fun JournalNoteDialog(
    onConfirm: (String) -> Unit,
    onCancel: () -> Unit,
    resetKey: Any,
) {
    var draft by remember(resetKey) { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onCancel,
        title = { Text(stringResource(R.string.today_note_dialog_title)) },
        text = {
            OutlinedTextField(
                value = draft,
                onValueChange = { draft = it },
                placeholder = { Text(stringResource(R.string.today_note_hint)) },
                singleLine = false,
                minLines = 3,
                modifier = Modifier.fillMaxWidth(),
            )
        },
        confirmButton = {
            TextButton(onClick = { onConfirm(draft) }) {
                Text(stringResource(R.string.today_note_ok))
            }
        },
        dismissButton = {
            TextButton(onClick = onCancel) {
                Text(stringResource(R.string.today_note_cancel))
            }
        },
    )
}

@Composable
private fun CompletedTaskDialog(
    taskText: String,
    onAddAnother: (String) -> Unit,
    onReset: () -> Unit,
    onCancel: () -> Unit,
    resetKey: Any,
) {
    var draft by remember(resetKey) { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onCancel,
        title = { Text(stringResource(R.string.today_done_dialog_title)) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(
                    text = taskText,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                OutlinedTextField(
                    value = draft,
                    onValueChange = { draft = it },
                    placeholder = { Text(stringResource(R.string.today_note_hint)) },
                    singleLine = false,
                    minLines = 3,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        },
        confirmButton = {
            TextButton(onClick = { onAddAnother(draft) }) {
                Text(stringResource(R.string.today_done_add_another))
            }
        },
        dismissButton = {
            // Material3's dismissButton slot accepts arbitrary content;
            // we stack two TextButtons here so all three actions (Add
            // another / Reset / Cancel) are visible on a single row.
            Row {
                TextButton(onClick = onReset) {
                    Text(stringResource(R.string.today_done_reset))
                }
                TextButton(onClick = onCancel) {
                    Text(stringResource(R.string.today_note_cancel))
                }
            }
        },
    )
}

// Date label like "Wed, May 28"; the year is omitted to keep the bar
// compact since most navigation stays within the current year.
private val DATE_NAV_FORMAT = DateTimeFormatter.ofPattern("EEE, MMM d")

@Composable
private fun DateNavBar(
    selectedDate: LocalDate,
    onPrevious: () -> Unit,
    onNext: () -> Unit,
    onToday: () -> Unit,
) {
    val label = if (selectedDate == LocalDate.now()) {
        stringResource(R.string.today_date_today)
    } else {
        selectedDate.format(DATE_NAV_FORMAT)
    }
    Row(
        modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        IconButton(onClick = onPrevious) {
            Text(
                text = "‹", // ‹
                style = MaterialTheme.typography.headlineMedium,
            )
        }
        // Tapping the label jumps back to the current day.
        Text(
            text = label,
            style = MaterialTheme.typography.titleMedium,
            textAlign = TextAlign.Center,
            modifier = Modifier
                .weight(1f)
                .clickable(onClick = onToday)
                .padding(vertical = 4.dp),
        )
        IconButton(onClick = onNext) {
            Text(
                text = "›", // ›
                style = MaterialTheme.typography.headlineMedium,
            )
        }
    }
}

@Composable
private fun AddTaskRow(onAdd: (String) -> Unit, enabled: Boolean) {
    var draft by remember { mutableStateOf("") }
    Row(
        modifier = Modifier.fillMaxWidth().padding(bottom = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        OutlinedTextField(
            value = draft,
            onValueChange = { draft = it },
            placeholder = { Text(stringResource(R.string.today_add_hint)) },
            singleLine = true,
            enabled = enabled,
            modifier = Modifier.weight(1f),
        )
        Button(
            onClick = {
                onAdd(draft)
                draft = ""
            },
            enabled = enabled && draft.isNotBlank(),
        ) {
            Text(stringResource(R.string.today_add_button))
        }
    }
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun TaskRow(
    task: TodayTask,
    onToggle: (Boolean) -> Unit,
    onDelete: () -> Unit,
) {
    var menuExpanded by remember { mutableStateOf(false) }
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Checkbox(checked = task.done, onCheckedChange = onToggle)
        // Anchoring the DropdownMenu inside this Box positions it near
        // the task text. combinedClickable on the Box makes the whole
        // text area a long-press target — a short tap is a no-op so it
        // doesn't compete with the Checkbox.
        Box(modifier = Modifier.weight(1f)) {
            Text(
                text = task.text,
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(min = 36.dp)
                    .combinedClickable(
                        onClick = {},
                        onLongClick = { menuExpanded = true },
                    )
                    .padding(vertical = 4.dp),
                style = MaterialTheme.typography.bodyLarge.copy(
                    textDecoration = if (task.done) TextDecoration.LineThrough else null,
                ),
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            DropdownMenu(
                expanded = menuExpanded,
                onDismissRequest = { menuExpanded = false },
            ) {
                DropdownMenuItem(
                    text = { Text(stringResource(R.string.today_remove_menu)) },
                    onClick = {
                        menuExpanded = false
                        onDelete()
                    },
                )
            }
        }
    }
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun WeekPlanRow(
    text: String,
    onAddToToday: () -> Unit,
) {
    var menuExpanded by remember { mutableStateOf(false) }
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        // Mirrors TaskRow: long-pressing the text opens a contextual menu,
        // here with the single "Add to today" action.
        Box(modifier = Modifier.weight(1f)) {
            Text(
                text = text,
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(min = 36.dp)
                    .combinedClickable(
                        onClick = {},
                        onLongClick = { menuExpanded = true },
                    )
                    .padding(vertical = 4.dp),
                style = MaterialTheme.typography.bodyLarge,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            DropdownMenu(
                expanded = menuExpanded,
                onDismissRequest = { menuExpanded = false },
            ) {
                DropdownMenuItem(
                    text = { Text(stringResource(R.string.today_week_plan_add)) },
                    onClick = {
                        menuExpanded = false
                        onAddToToday()
                    },
                )
            }
        }
    }
}

@Composable
private fun EmptyState(text: String) {
    // verticalScroll keeps the empty state pull-to-refresh-friendly:
    // PullToRefreshBox detects the gesture via nestedScroll, so the content
    // must be a vertically scrollable layout even when there's nothing to scroll.
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
            text = stringResource(R.string.today_error_format).format(message),
            color = MaterialTheme.colorScheme.onErrorContainer,
            modifier = Modifier.weight(1f),
        )
        TextButton(onClick = onDismiss) {
            Text(stringResource(R.string.today_dismiss_error))
        }
    }
}
