package org.polybrain.tasks.health.data

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.longPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.core.stringSetPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import org.polybrain.tasks.health.BuildConfig

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
        // Fall back to build-time defaults (injected from android/local.properties
        // or env vars on debug builds; empty on release) when DataStore is blank.
        // This lets a fresh debug install of the app come up already pointed at
        // the dev server without needing to type into Settings every time.
        SettingsSnapshot(
            serverUrl = prefs[SERVER_URL].orEmpty()
                .ifBlank { BuildConfig.DEV_SERVER_URL },
            apiToken = prefs[API_TOKEN].orEmpty()
                .ifBlank { BuildConfig.DEV_API_TOKEN },
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

    /**
     * IDs of bike-ride sessions already posted to the server. Used by
     * [HealthSyncWorker] to avoid re-posting the same ride on each 7-day
     * window re-sync. Kept as an opaque set — we don't need ordering or
     * timestamps because sessions don't mutate after they finish.
     */
    suspend fun syncedBikeSessionIds(): Set<String> =
        context.dataStore.data.first()[SYNCED_BIKE_SESSION_IDS].orEmpty()

    suspend fun addSyncedBikeSessionIds(ids: Collection<String>) {
        if (ids.isEmpty()) return
        context.dataStore.edit { prefs ->
            val existing = prefs[SYNCED_BIKE_SESSION_IDS].orEmpty()
            prefs[SYNCED_BIKE_SESSION_IDS] = existing + ids
        }
    }

    /**
     * Story ids whose trips are currently being location-tracked on this phone.
     * The local source of truth for whether [TripLocationService] should run:
     * survives an app kill (tracking resumes on reopen) but not a reboot.
     */
    suspend fun trackedStoryIds(): Set<String> =
        context.dataStore.data.first()[TRACKED_STORY_IDS].orEmpty()

    suspend fun addTrackedStoryId(id: Long) {
        context.dataStore.edit { prefs ->
            prefs[TRACKED_STORY_IDS] = prefs[TRACKED_STORY_IDS].orEmpty() + id.toString()
        }
    }

    suspend fun removeTrackedStoryId(id: Long) {
        context.dataStore.edit { prefs ->
            prefs[TRACKED_STORY_IDS] = prefs[TRACKED_STORY_IDS].orEmpty() - id.toString()
        }
    }

    suspend fun replaceTrackedStoryIds(ids: Collection<Long>) {
        context.dataStore.edit { prefs ->
            prefs[TRACKED_STORY_IDS] = ids.map { it.toString() }.toSet()
        }
    }

    private companion object {
        val SERVER_URL = stringPreferencesKey("server_url")
        val API_TOKEN = stringPreferencesKey("api_token")
        val LAST_SYNC_MS = longPreferencesKey("last_sync_ms")
        val LAST_SYNC_ERROR = stringPreferencesKey("last_sync_error")
        val SYNCED_BIKE_SESSION_IDS = stringSetPreferencesKey("synced_bike_session_ids")
        val TRACKED_STORY_IDS = stringSetPreferencesKey("tracked_story_ids")
    }
}
