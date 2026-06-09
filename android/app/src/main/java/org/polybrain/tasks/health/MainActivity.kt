package org.polybrain.tasks.health

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Menu
import androidx.compose.material3.DrawerValue
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalDrawerSheet
import androidx.compose.material3.ModalNavigationDrawer
import androidx.compose.material3.NavigationDrawerItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.rememberDrawerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import java.time.LocalDate
import kotlinx.coroutines.launch
import org.polybrain.tasks.health.ui.BoardPickerScreen
import org.polybrain.tasks.health.ui.HealthScreen
import org.polybrain.tasks.health.ui.MainViewModel
import org.polybrain.tasks.health.ui.SettingsScreen
import org.polybrain.tasks.health.ui.TodayScreen
import org.polybrain.tasks.health.ui.photo.AddPhotoViewModel
import org.polybrain.tasks.health.ui.trip.AddPhotoDialog
import org.polybrain.tasks.health.ui.trip.TripDetailScreen
import org.polybrain.tasks.health.ui.trip.TripsScreen

private enum class Destination(val titleRes: Int) {
    Today(R.string.nav_today),
    Trips(R.string.nav_trips),
    Health(R.string.nav_health),
    Settings(R.string.nav_settings),
}

class MainActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                Surface(color = MaterialTheme.colorScheme.background) {
                    MainScaffold()
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun MainScaffold(vm: MainViewModel = viewModel()) {
    var current by remember { mutableStateOf(Destination.Today) }
    var tripDetailId by remember { mutableStateOf<Long?>(null) }
    // Non-null while the board picker is open; holds the Today day the picked
    // items will be added to.
    var boardPickerDate by remember { mutableStateOf<LocalDate?>(null) }
    val drawerState = rememberDrawerState(initialValue = DrawerValue.Closed)
    val scope = rememberCoroutineScope()

    // Standalone "Add Photo" flow, launched from the Today FAB. The picker
    // hands a content Uri to the view model, which opens the photo dialog.
    val addPhotoVm: AddPhotoViewModel = viewModel()
    val photoDialogOpen by addPhotoVm.dialogOpen.collectAsState()
    val photoPicker = rememberLauncherForActivityResult(
        ActivityResultContracts.PickVisualMedia(),
    ) { uri -> if (uri != null) addPhotoVm.openAddPhoto(uri) }

    // Standalone photos have no screen showing their outbox state, so delivery
    // results (uploaded / failed / couldn't queue) surface here as snackbars.
    val snackbarHostState = remember { SnackbarHostState() }
    val context = LocalContext.current
    LaunchedEffect(addPhotoVm) {
        addPhotoVm.events.collect { event ->
            val message = when (event) {
                is AddPhotoViewModel.UploadEvent.Uploaded ->
                    context.resources.getQuantityString(
                        R.plurals.photo_uploaded, event.count, event.count,
                    )
                is AddPhotoViewModel.UploadEvent.Failed ->
                    context.getString(
                        if (event.willRetry) R.string.photo_upload_failed_retry
                        else R.string.photo_upload_failed,
                        event.error,
                    )
                is AddPhotoViewModel.UploadEvent.QueueFailed ->
                    context.getString(R.string.photo_queue_failed, event.error)
            }
            snackbarHostState.showSnackbar(message)
        }
    }

    BackHandler(enabled = tripDetailId != null) {
        tripDetailId = null
    }

    BackHandler(enabled = boardPickerDate != null) {
        boardPickerDate = null
    }

    ModalNavigationDrawer(
        drawerState = drawerState,
        drawerContent = {
            ModalDrawerSheet {
                Spacer(Modifier.height(12.dp))
                Text(
                    text = stringResource(R.string.app_name),
                    style = MaterialTheme.typography.titleLarge,
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 12.dp),
                )
                Destination.entries.forEach { dest ->
                    NavigationDrawerItem(
                        label = { Text(stringResource(dest.titleRes)) },
                        selected = dest == current,
                        onClick = {
                            current = dest
                            tripDetailId = null
                            boardPickerDate = null
                            scope.launch { drawerState.close() }
                        },
                        modifier = Modifier.padding(horizontal = 12.dp),
                    )
                }
            }
        },
    ) {
        Scaffold(
            snackbarHost = { SnackbarHost(snackbarHostState) },
            topBar = {
                TopAppBar(
                    // The Today screen's top bar carries the product name
                    // ("Tasks Collector"); the drawer item stays "Today".
                    // Other destinations show their own nav title.
                    title = {
                        val titleRes = if (current == Destination.Today) {
                            R.string.today_top_bar_title
                        } else {
                            current.titleRes
                        }
                        Text(stringResource(titleRes))
                    },
                    navigationIcon = {
                        IconButton(onClick = { scope.launch { drawerState.open() } }) {
                            Icon(
                                imageVector = Icons.Filled.Menu,
                                contentDescription = stringResource(R.string.nav_open_menu),
                            )
                        }
                    },
                )
            },
        ) { innerPadding ->
            Surface(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(innerPadding),
                color = MaterialTheme.colorScheme.background,
            ) {
                when (current) {
                    Destination.Today -> {
                        val pickerDate = boardPickerDate
                        if (pickerDate != null) {
                            BoardPickerScreen(
                                selectedDate = pickerDate,
                                onDone = { boardPickerDate = null },
                                onCancel = { boardPickerDate = null },
                            )
                        } else {
                            TodayScreen(
                                onAddFromBoard = { boardPickerDate = it },
                                onAddPhoto = {
                                    photoPicker.launch(
                                        PickVisualMediaRequest(
                                            ActivityResultContracts.PickVisualMedia.ImageOnly
                                        )
                                    )
                                },
                            )
                        }
                        if (photoDialogOpen) {
                            val gps by addPhotoVm.gps.collectAsState()
                            val selectedPhoto by addPhotoVm.selectedPhoto.collectAsState()
                            AddPhotoDialog(
                                selectedPhoto = selectedPhoto,
                                gps = gps,
                                onPermissionResult = addPhotoVm::onLocationPermissionResult,
                                onSend = addPhotoVm::sendPhoto,
                                onDismiss = addPhotoVm::closeAddPhoto,
                            )
                        }
                    }
                    Destination.Trips -> {
                        val detailId = tripDetailId
                        if (detailId != null) {
                            TripDetailScreen(storyId = detailId)
                        } else {
                            TripsScreen(onOpenTrip = { tripDetailId = it })
                        }
                    }
                    Destination.Health -> HealthScreen(vm)
                    Destination.Settings -> SettingsScreen(vm)
                }
            }
        }
    }
}
