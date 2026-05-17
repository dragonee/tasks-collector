package com.dragonee.tasks.health.sync

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.dragonee.tasks.health.data.HealthRepository
import com.dragonee.tasks.health.data.Settings
import com.dragonee.tasks.health.data.TasksClient
import com.dragonee.tasks.health.data.TrackHabitRequest
import java.time.LocalDate
import java.time.ZoneId

class HealthSyncWorker(
    appContext: Context,
    params: WorkerParameters,
) : CoroutineWorker(appContext, params) {

    private val settings = Settings(applicationContext)
    private val health = HealthRepository(applicationContext)

    override suspend fun doWork(): Result {
        val snapshot = settings.snapshot()
        if (!snapshot.isConfigured) {
            settings.recordSyncFailure("Server URL or API token not set")
            return Result.failure()
        }

        return try {
            if (!health.hasAllPermissions()) {
                settings.recordSyncFailure("Health Connect permissions not granted")
                return Result.failure()
            }

            val api = TasksClient.build(snapshot.serverUrl, snapshot.apiToken)
            val today = LocalDate.now(ZoneId.systemDefault())

            // Re-sync the trailing window from oldest to newest. Wearables
            // sometimes back-fill earlier days after re-connecting, so a
            // single sync per day isn't enough — older days can still change.
            for (offset in (SYNC_WINDOW_DAYS - 1) downTo 0) {
                val day = today.minusDays(offset.toLong())
                val metrics = health.aggregateDay(day)
                val note = NoteFormatter.format(metrics)
                api.trackHabit(
                    TrackHabitRequest(
                        keyword = HABIT_KEYWORD,
                        date = day.toString(),
                        note = note,
                    )
                )
            }

            settings.recordSyncSuccess(System.currentTimeMillis())
            Result.success()
        } catch (t: Throwable) {
            settings.recordSyncFailure(t.message ?: t::class.java.simpleName)
            Result.retry()
        }
    }

    companion object {
        const val HABIT_KEYWORD = "health-metrics"

        /** Days re-synced per run, counting today. Covers late wearable back-fills. */
        const val SYNC_WINDOW_DAYS = 7
    }
}
