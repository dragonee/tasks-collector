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
 * outbox. The service runs whenever that set is non-empty *and* tracking isn't
 * paused ([Settings.trackingPaused]); when the set empties (the last active
 * trip stopped) the service is stopped and the breadcrumb log is cleared.
 *
 * Pause/resume is decoupled from the trip lifecycle: pausing stops sampling but
 * keeps the trail, so resuming continues the same log. The trail is dropped
 * *only* on finish (the set going empty), never on pause.
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

    /** Pause breadcrumb sampling without ending the trip or dropping the trail. */
    suspend fun pause(context: Context) {
        val settings = Settings(context.applicationContext)
        settings.setTrackingPaused(true)
        ensureService(context.applicationContext, settings)
    }

    /** Resume breadcrumb sampling, continuing the existing trail. */
    suspend fun resume(context: Context) {
        val settings = Settings(context.applicationContext)
        settings.setTrackingPaused(false)
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
        if (settings.trackedStoryIds().isEmpty()) {
            // No active trip owns the trail anymore — stop and drop it. Clearing
            // the trail happens ONLY here (finish), never on pause. Reset the
            // pause flag so the next trip starts sampling unpaused.
            appContext.stopService(intent)
            BreadcrumbStore(appContext).clear()
            if (settings.trackingPaused()) settings.setTrackingPaused(false)
            return
        }
        if (settings.trackingPaused()) {
            // Trip still active, but the user paused sampling: stop the service
            // (the notification clears; stopService cancels the START_STICKY
            // restart) but keep the trail so resume continues it.
            appContext.stopService(intent)
            return
        }
        // Without the fine-location grant the service could never promote
        // itself to a location-type FGS (Android 14+ throws), and bailing out
        // inside onStartCommand still trips the startForeground deadline
        // (ForegroundServiceDidNotStartInTimeException) — so the service must
        // not be started at all. The tracked ids are kept: the next
        // ensureService call after the user grants location brings it up. Note
        // we don't stop a possibly-running service here — a permission-read
        // race shouldn't tear down active tracking.
        if (!hasFineLocation(appContext)) return
        ContextCompat.startForegroundService(appContext, intent)
    }

    private fun hasFineLocation(context: Context): Boolean =
        ContextCompat.checkSelfPermission(
            context, Manifest.permission.ACCESS_FINE_LOCATION,
        ) == PackageManager.PERMISSION_GRANTED
}
