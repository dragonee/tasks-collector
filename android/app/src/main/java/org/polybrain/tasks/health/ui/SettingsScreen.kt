package org.polybrain.tasks.health.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import org.polybrain.tasks.health.R

/**
 * Which server the app talks to, and as whom. "Log in" opens the server in
 * the browser, where the user logs in as they do on the web; the phone comes
 * back with a token of its own (see `data/OAuthLogin.kt`). A token can still
 * be pasted in instead.
 */
@Composable
fun SettingsScreen(vm: MainViewModel) {
    val state by vm.settingsState.collectAsState()
    val busy by vm.loginBusy.collectAsState()
    val loginError by vm.loginError.collectAsState()
    val uriHandler = LocalUriHandler.current

    var url by remember { mutableStateOf("") }
    var token by remember { mutableStateOf("") }
    LaunchedEffect(state.serverUrl) {
        if (url.isEmpty()) url = state.serverUrl
    }
    // The token changes under the field when the phone logs in or out; what
    // the field holds must not be an old one that Save would put back.
    LaunchedEffect(state.apiToken) {
        token = state.apiToken
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        OutlinedTextField(
            value = url,
            onValueChange = { url = it },
            label = { Text(stringResource(R.string.server_url_label)) },
            placeholder = { Text(stringResource(R.string.server_url_placeholder)) },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )

        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(
                onClick = { vm.startLogin(url) { uriHandler.openUri(it) } },
                enabled = url.isNotBlank() && !busy,
            ) {
                Text(stringResource(R.string.login_button))
            }
            if (state.isConfigured) {
                OutlinedButton(onClick = vm::logout, enabled = !busy) {
                    Text(stringResource(R.string.logout_button))
                }
            }
        }

        val error = loginError
        when {
            busy -> Text(stringResource(R.string.login_busy))
            error != null -> Text(
                text = stringResource(R.string.login_failed, error),
                color = MaterialTheme.colorScheme.error,
            )
            state.isConfigured -> Text(stringResource(R.string.login_done, state.serverUrl))
            else -> Text(
                text = stringResource(R.string.login_hint),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }

        HorizontalDivider()

        OutlinedTextField(
            value = token,
            onValueChange = { token = it },
            label = { Text(stringResource(R.string.api_token_label)) },
            singleLine = true,
            visualTransformation = PasswordVisualTransformation(),
            modifier = Modifier.fillMaxWidth(),
        )

        Button(
            onClick = { vm.save(url, token) },
            enabled = url.isNotBlank() && token.isNotBlank(),
        ) {
            Text(stringResource(R.string.save))
        }
    }
}
