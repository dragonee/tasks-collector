package org.polybrain.tasks.health.location

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import androidx.core.content.ContextCompat
import org.polybrain.tasks.health.data.BreadcrumbStore
import org.polybrain.tasks.health.data.Settings

/**
 * Drives [TripLocationService]'s lifecycle off the set of locally-tracked
 * trips ([Settings.trackedStoryIds]) — the analogue of `SyncScheduler` for the
 * outbox. The service runs whenever that set is non-empty; when it empties
 * (the last active trip stopped) the service is stopped and the breadcrumb log
 * is cleared.
 *
 * All entry points are `suspend` because they touch DataStore; call them from
 * a coroutine (the trip ViewModels already do).
 */
object TripTracker {

    /** Begin tracking a newly started trip. */
    suspend fun start(context: Context, storyId: Long) {
        val settings = Settings(context.applicationContext)
        settings.addTrackedStoryId(storyId)
        ensureService(context.applicationContext, settings)
    }

    /** Stop tracking a trip that was just stopped. */
    suspend fun stop(context: Context, storyId: Long) {
        val settings = Settings(context.applicationContext)
        settings.removeTrackedStoryId(storyId)
        ensureService(context.applicationContext, settings)
    }

    /**
     * Align tracking with the server's current active trips (e.g. a trip
     * stopped from the web turns tracking off; one started elsewhere turns it
     * on). Call after a trip-list reload.
     */
    suspend fun reconcile(context: Context, activeIds: Collection<Long>) {
        val settings = Settings(context.applicationContext)
        settings.replaceTrackedStoryIds(activeIds)
        ensureService(context.applicationContext, settings)
    }

    /** Restart the service on app open if trips were being tracked (post app-kill). */
    suspend fun resumeIfNeeded(context: Context) {
        ensureService(context.applicationContext, Settings(context.applicationContext))
    }

    private suspend fun ensureService(appContext: Context, settings: Settings) {
        val intent = Intent(appContext, TripLocationService::class.java)
        if (settings.trackedStoryIds().isNotEmpty()) {
            // Without the fine-location grant the service could never promote
            // itself to a location-type FGS (Android 14+ throws), and bailing
            // out inside onStartCommand still trips the startForeground
            // deadline (ForegroundServiceDidNotStartInTimeException) — so the
            // service must not be started at all. The tracked ids are kept:
            // the next ensureService call after the user grants location
            // brings the service up.
            if (!hasFineLocation(appContext)) return
            ContextCompat.startForegroundService(appContext, intent)
        } else {
            appContext.stopService(intent)
            // No active trip owns the trail anymore — drop it.
            BreadcrumbStore(appContext).clear()
        }
    }

    private fun hasFineLocation(context: Context): Boolean =
        ContextCompat.checkSelfPermission(
            context, Manifest.permission.ACCESS_FINE_LOCATION,
        ) == PackageManager.PERMISSION_GRANTED
}
