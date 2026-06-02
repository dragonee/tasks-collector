package org.polybrain.tasks.health.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import java.time.LocalDate
import org.polybrain.tasks.health.R
import org.polybrain.tasks.health.data.BoardItem

// MoSCoW buckets in priority order. Ids and colors mirror the web frontend
// (tasks/assets/components/Moscow.vue); the "Unclassified" pseudo-bucket maps
// to BoardPickerViewModel.FILTER_NONE and catches items with no moscow marker.
private data class MoscowBucket(val id: String, val labelRes: Int, val color: Color)

private val MOSCOW_BUCKETS = listOf(
    MoscowBucket("must", R.string.board_picker_filter_must, Color(0xFFB91C1C)),
    MoscowBucket("should", R.string.board_picker_filter_should, Color(0xFFD97706)),
    MoscowBucket("could", R.string.board_picker_filter_could, Color(0xFF0D9488)),
    MoscowBucket("wont", R.string.board_picker_filter_wont, Color(0xFF64748B)),
    MoscowBucket(
        BoardPickerViewModel.FILTER_NONE,
        R.string.board_picker_filter_none,
        Color(0xFFBDBDBD),
    ),
)

private val BUCKET_BY_ID = MOSCOW_BUCKETS.associateBy { it.id }

// Depth indentation step (dp per level); capped so deeply-nested items keep
// readable width.
private const val MAX_INDENT_DEPTH = 6
private const val INDENT_STEP_DP = 16

@Composable
fun BoardPickerScreen(
    selectedDate: LocalDate,
    onDone: () -> Unit,
    onCancel: () -> Unit,
    vm: BoardPickerViewModel = viewModel(),
) {
    val items by vm.items.collectAsState()
    val loading by vm.loading.collectAsState()
    val error by vm.error.collectAsState()
    val configured by vm.configured.collectAsState()
    val selected by vm.selected.collectAsState()
    val filter by vm.moscowFilter.collectAsState()

    LaunchedEffect(Unit) { vm.refresh() }

    val visibleItems = BoardPickerViewModel.applyFilter(items, filter)

    Column(modifier = Modifier.fillMaxSize().padding(16.dp)) {
        error?.let { ErrorBanner(message = it, onDismiss = vm::clearError) }

        FilterChipRow(
            active = filter,
            onToggle = vm::toggleFilter,
        )

        HorizontalDivider(modifier = Modifier.padding(vertical = 8.dp))

        Box(modifier = Modifier.weight(1f).fillMaxWidth()) {
            when {
                !configured -> CenteredMessage(stringResource(R.string.today_not_configured))
                loading && items.isEmpty() ->
                    CircularProgressIndicator(modifier = Modifier.align(Alignment.Center))
                items.isEmpty() -> CenteredMessage(stringResource(R.string.board_picker_empty))
                // No item key: a board can hold duplicate texts across nodes,
                // which would collide as LazyColumn keys. Positional keys are
                // fine — rows are stateless (checked state lives in the VM).
                else -> LazyColumn(modifier = Modifier.fillMaxSize()) {
                    items(items = visibleItems) { item ->
                        BoardItemRow(
                            item = item,
                            checked = item.text in selected,
                            onToggle = { vm.toggleSelection(item.text) },
                        )
                    }
                }
            }
        }

        HorizontalDivider(modifier = Modifier.padding(vertical = 8.dp))

        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Button(
                onClick = { vm.addSelected(selectedDate.toString(), onDone) },
                enabled = selected.isNotEmpty(),
                modifier = Modifier.weight(1f),
            ) {
                Text(stringResource(R.string.board_picker_add_button, selected.size))
            }
            TextButton(onClick = onCancel) {
                Text(stringResource(R.string.board_picker_cancel))
            }
        }
    }
}

@Composable
private fun FilterChipRow(active: Set<String>, onToggle: (String) -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .horizontalScroll(rememberScrollState()),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        MOSCOW_BUCKETS.forEach { bucket ->
            FilterChip(
                selected = bucket.id in active,
                onClick = { onToggle(bucket.id) },
                label = { Text(stringResource(bucket.labelRes)) },
            )
        }
    }
}

@Composable
private fun BoardItemRow(
    item: BoardItem,
    checked: Boolean,
    onToggle: () -> Unit,
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Checkbox(checked = checked, onCheckedChange = { onToggle() })
        Text(
            text = item.text,
            modifier = Modifier
                .weight(1f)
                .heightIn(min = 36.dp)
                .padding(
                    // Indent by tree depth (capped) to reflect nesting.
                    start = (minOf(item.depth, MAX_INDENT_DEPTH) * INDENT_STEP_DP).dp,
                    top = 4.dp,
                    bottom = 4.dp,
                ),
            style = MaterialTheme.typography.bodyLarge.copy(
                textDecoration = if (item.done) TextDecoration.LineThrough else null,
            ),
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        MoscowBadge(item.moscow)
    }
}

@Composable
private fun MoscowBadge(moscow: String?) {
    // null moscow is shown as the "Unclassified" pseudo-bucket dot.
    val bucket = BUCKET_BY_ID[moscow ?: BoardPickerViewModel.FILTER_NONE] ?: return
    Box(
        modifier = Modifier
            .padding(start = 8.dp, end = 4.dp)
            .size(12.dp)
            .clip(CircleShape)
            .background(bucket.color),
    )
}

@Composable
private fun CenteredMessage(text: String) {
    Box(
        modifier = Modifier.fillMaxSize().padding(24.dp),
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
