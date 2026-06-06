package org.polybrain.tasks.health.ui.trip

import android.Manifest
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
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
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import org.polybrain.tasks.health.R
import org.polybrain.tasks.health.data.TripSummary

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TripsScreen(
    onOpenTrip: (Long) -> Unit,
    vm: TripsViewModel = viewModel(),
) {
    val active by vm.active.collectAsState()
    val history by vm.history.collectAsState()
    val total by vm.totalHistory.collectAsState()
    val loading by vm.loading.collectAsState()
    val error by vm.error.collectAsState()
    val configured by vm.configured.collectAsState()
    val focus by vm.focusTrip.collectAsState()

    LaunchedEffect(Unit) { vm.refresh() }
    LaunchedEffect(focus) {
        focus?.let {
            vm.onFocusConsumed()
            onOpenTrip(it)
        }
    }

    // Starting a trip turns on location tracking, so ask for the permissions it
    // needs first (location to sample; notifications for the ongoing service
    // notice on Android 13+). The trip starts once the user responds either way.
    val trackingPermissions = remember {
        buildList {
            add(Manifest.permission.ACCESS_FINE_LOCATION)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                add(Manifest.permission.POST_NOTIFICATIONS)
            }
        }.toTypedArray()
    }
    val startTripLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions(),
    ) { vm.startTrip() }

    Column(modifier = Modifier.fillMaxSize().padding(16.dp)) {
        error?.let { ErrorBanner(message = it, onDismiss = vm::clearError) }

        PullToRefreshBox(
            isRefreshing = loading,
            onRefresh = vm::refresh,
            modifier = Modifier.fillMaxSize(),
        ) {
            if (!configured) {
                EmptyState(stringResource(R.string.trips_not_configured))
            } else {
                LazyColumn(
                    modifier = Modifier.fillMaxSize(),
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    item {
                        Button(
                            onClick = { startTripLauncher.launch(trackingPermissions) },
                            modifier = Modifier.fillMaxWidth(),
                        ) {
                            Text(stringResource(R.string.trips_start_button))
                        }
                    }

                    if (active.isNotEmpty()) {
                        item {
                            SectionHeader(stringResource(R.string.trips_active_heading))
                        }
                        items(items = active, key = { "a-${it.id}" }) { trip ->
                            TripRow(trip = trip, onClick = { onOpenTrip(trip.id) })
                        }
                    }

                    item {
                        SectionHeader(stringResource(R.string.trips_history_heading))
                    }
                    if (history.isEmpty()) {
                        item {
                            Text(
                                text = stringResource(R.string.trips_history_empty),
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    } else {
                        items(items = history, key = { "h-${it.id}" }) { trip ->
                            TripRow(trip = trip, onClick = { onOpenTrip(trip.id) })
                        }
                        if (history.size < total) {
                            item {
                                OutlinedButton(
                                    onClick = vm::loadMoreHistory,
                                    modifier = Modifier.fillMaxWidth(),
                                ) {
                                    Text(stringResource(R.string.trips_history_load_more))
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun SectionHeader(text: String) {
    Text(
        text = text,
        style = MaterialTheme.typography.titleMedium,
        modifier = Modifier.padding(top = 8.dp),
    )
}

@Composable
private fun TripRow(trip: TripSummary, onClick: () -> Unit) {
    TextButton(
        onClick = onClick,
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(modifier = Modifier.fillMaxWidth()) {
            Text(
                text = trip.title,
                style = MaterialTheme.typography.bodyLarge,
            )
            Text(
                text = formatTripRange(trip.started, trip.stopped),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
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
