package org.polybrain.tasks.health.ui.trip

import android.content.ActivityNotFoundException
import android.content.Intent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.unit.dp
import org.polybrain.tasks.health.R
import org.polybrain.tasks.health.data.TripShare

/**
 * Public-link dialog for a trip. Stays open across create/unshare so the
 * user sees the state flip: not shared (explainer + "Create link") versus
 * shared (the URL + copy / system share sheet / unshare).
 */
@Composable
fun ShareTripDialog(
    share: TripShare?,
    busy: Boolean,
    onCreate: () -> Unit,
    onUnshare: () -> Unit,
    onDismiss: () -> Unit,
) {
    val context = LocalContext.current
    val clipboard = LocalClipboardManager.current

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(stringResource(R.string.trip_share_dialog_title)) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                if (share == null) {
                    Text(stringResource(R.string.trip_share_not_shared))
                } else {
                    Text(
                        text = stringResource(R.string.trip_share_shared_hint),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    SelectionContainer {
                        Text(
                            text = share.url,
                            style = MaterialTheme.typography.bodySmall,
                        )
                    }
                    TextButton(
                        onClick = { clipboard.setText(AnnotatedString(share.url)) },
                    ) {
                        Text(stringResource(R.string.trip_share_copy))
                    }
                    TextButton(
                        onClick = {
                            val send = Intent(Intent.ACTION_SEND).apply {
                                type = "text/plain"
                                putExtra(Intent.EXTRA_TEXT, share.url)
                            }
                            try {
                                context.startActivity(Intent.createChooser(send, null))
                            } catch (_: ActivityNotFoundException) {
                                // No app can handle plain-text sharing; the URL
                                // is still visible and copyable in the dialog.
                            }
                        },
                    ) {
                        Text(stringResource(R.string.trip_share_send))
                    }
                    TextButton(
                        onClick = onUnshare,
                        enabled = !busy,
                    ) {
                        Text(
                            text = stringResource(R.string.trip_share_unshare),
                            color = MaterialTheme.colorScheme.error,
                        )
                    }
                }
            }
        },
        confirmButton = {
            if (share == null) {
                TextButton(onClick = onCreate, enabled = !busy) {
                    Text(stringResource(R.string.trip_share_create))
                }
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text(stringResource(R.string.trip_share_close))
            }
        },
    )
}
