package com.dragonee.tasks.health.data

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.longPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map

private val Context.dataStore: DataStore<Preferences> by preferencesDataStore(name = "settings")

data class SettingsSnapshot(
    val serverUrl: String,
    val apiToken: String,
    val lastSyncEpochMs: Long,
    val lastSyncError: String,
) {
    val isConfigured: Boolean get() = serverUrl.isNotBlank() && apiToken.isNotBlank()
}

class Settings(private val context: Context) {

    val flow: Flow<SettingsSnapshot> = context.dataStore.data.map { prefs ->
        SettingsSnapshot(
            serverUrl = prefs[SERVER_URL].orEmpty(),
            apiToken = prefs[API_TOKEN].orEmpty(),
            lastSyncEpochMs = prefs[LAST_SYNC_MS] ?: 0L,
            lastSyncError = prefs[LAST_SYNC_ERROR].orEmpty(),
        )
    }

    suspend fun snapshot(): SettingsSnapshot = flow.first()

    suspend fun saveServerConfig(url: String, token: String) {
        context.dataStore.edit { prefs ->
            prefs[SERVER_URL] = url.trim()
            prefs[API_TOKEN] = token.trim()
        }
    }

    suspend fun recordSyncSuccess(epochMs: Long) {
        context.dataStore.edit { prefs ->
            prefs[LAST_SYNC_MS] = epochMs
            prefs.remove(LAST_SYNC_ERROR)
        }
    }

    suspend fun recordSyncFailure(error: String) {
        context.dataStore.edit { prefs ->
            prefs[LAST_SYNC_ERROR] = error
        }
    }

    private companion object {
        val SERVER_URL = stringPreferencesKey("server_url")
        val API_TOKEN = stringPreferencesKey("api_token")
        val LAST_SYNC_MS = longPreferencesKey("last_sync_ms")
        val LAST_SYNC_ERROR = stringPreferencesKey("last_sync_error")
    }
}
