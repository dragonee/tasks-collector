package org.polybrain.tasks.health.sync

import android.content.Context
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import java.time.Duration
import java.util.concurrent.TimeUnit

object SyncScheduler {

    private const val PERIODIC = "health-sync-periodic"
    private const val DAILY = "health-sync-daily"
    private const val ONE_OFF = "health-sync-once"

    /** Unique-work name for the trip-outbox drain (see [OutboxWorker]). */
    const val OUTBOX = "outbox-drain"

    private val networkConstraints = Constraints.Builder()
        .setRequiredNetworkType(NetworkType.CONNECTED)
        .build()

    /** Enqueues both the hourly best-effort job and the daily backstop. */
    fun schedule(context: Context) {
        schedulePeriodic(context)
        scheduleDaily(context)
    }

    fun schedulePeriodic(context: Context) {
        val request = PeriodicWorkRequestBuilder<HealthSyncWorker>(Duration.ofHours(1))
            .setConstraints(networkConstraints)
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 5, TimeUnit.MINUTES)
            .build()

        WorkManager.getInstance(context).enqueueUniquePeriodicWork(
            PERIODIC,
            ExistingPeriodicWorkPolicy.UPDATE,
            request,
        )
    }

    /**
     * Daily backstop. WorkManager picks a time within each 24-hour window to
     * run the job, respecting Doze and battery state. The hourly periodic job
     * still runs alongside this; the daily job exists so that a day never
     * passes without at least one successful sync attempt even if Doze or
     * throttling defers the hourly worker.
     */
    fun scheduleDaily(context: Context) {
        val request = PeriodicWorkRequestBuilder<HealthSyncWorker>(Duration.ofDays(1))
            .setConstraints(networkConstraints)
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 1, TimeUnit.HOURS)
            .build()

        WorkManager.getInstance(context).enqueueUniquePeriodicWork(
            DAILY,
            ExistingPeriodicWorkPolicy.UPDATE,
            request,
        )
    }

    fun runOnce(context: Context) {
        val request = OneTimeWorkRequestBuilder<HealthSyncWorker>()
            .setConstraints(networkConstraints)
            .build()
        WorkManager.getInstance(context).enqueueUniqueWork(
            ONE_OFF,
            ExistingWorkPolicy.REPLACE,
            request,
        )
    }

    /**
     * Kick the trip-outbox drain. Network-constrained so it waits for
     * connectivity, with exponential backoff between retries. Enqueued as
     * APPEND_OR_REPLACE so an item added while a drain is mid-flight still gets
     * a fresh pass afterwards; the worker is idempotent (re-reads the queue,
     * server dedupes on the idempotency key), so an extra pass is harmless.
     *
     * Safe to call on app start to resume after a reboot/kill.
     */
    fun drainOutbox(context: Context) {
        val request = OneTimeWorkRequestBuilder<OutboxWorker>()
            .setConstraints(networkConstraints)
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
            .build()
        WorkManager.getInstance(context).enqueueUniqueWork(
            OUTBOX,
            ExistingWorkPolicy.APPEND_OR_REPLACE,
            request,
        )
    }

    fun cancelAll(context: Context) {
        val wm = WorkManager.getInstance(context)
        wm.cancelUniqueWork(PERIODIC)
        wm.cancelUniqueWork(DAILY)
        wm.cancelUniqueWork(ONE_OFF)
        wm.cancelUniqueWork(OUTBOX)
    }
}
