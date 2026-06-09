package org.polybrain.tasks.health.sync

import android.content.Context
import androidx.core.content.ContextCompat
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkInfo
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
     * connectivity, with exponential backoff between retries.
     *
     * While a drain is actively RUNNING the kick is APPENDed so the mid-flight
     * pass finishes and a fresh one follows. Otherwise the existing chain is
     * REPLACEd: after a string of failures the chain sits in exponential
     * backoff (hours, eventually), and APPEND would park this kick — and every
     * later one — behind that wait; a user-initiated kick should retry *now*.
     * Replacing is safe because the worker is idempotent: it re-reads the
     * queue, a photo's upload resume flags are persisted, and the server
     * dedupes on the idempotency key. The check-then-enqueue race (a worker
     * starting in between and getting cancelled) is harmless for the same
     * reason.
     *
     * Safe to call on app start to resume after a reboot/kill.
     */
    fun drainOutbox(context: Context) {
        val wm = WorkManager.getInstance(context)
        val request = OneTimeWorkRequestBuilder<OutboxWorker>()
            .setConstraints(networkConstraints)
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
            .build()
        val infos = wm.getWorkInfosForUniqueWork(OUTBOX)
        infos.addListener({
            val running = runCatching { infos.get() }
                .getOrDefault(emptyList())
                .any { it.state == WorkInfo.State.RUNNING }
            val policy =
                if (running) ExistingWorkPolicy.APPEND_OR_REPLACE
                else ExistingWorkPolicy.REPLACE
            wm.enqueueUniqueWork(OUTBOX, policy, request)
        }, ContextCompat.getMainExecutor(context))
    }

    fun cancelAll(context: Context) {
        val wm = WorkManager.getInstance(context)
        wm.cancelUniqueWork(PERIODIC)
        wm.cancelUniqueWork(DAILY)
        wm.cancelUniqueWork(ONE_OFF)
        wm.cancelUniqueWork(OUTBOX)
    }
}
