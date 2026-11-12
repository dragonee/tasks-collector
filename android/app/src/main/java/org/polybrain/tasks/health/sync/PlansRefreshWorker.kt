package org.polybrain.tasks.health.sync

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import java.time.LocalDate
import org.polybrain.tasks.health.data.SavedPlans
import org.polybrain.tasks.health.data.Settings
import org.polybrain.tasks.health.data.TasksClient
import org.polybrain.tasks.health.data.refresh

/**
 * Keeps today's and tomorrow's plans on the phone ([SavedPlans]), so that a
 * plan written on the web in the evening is on the Today list the next
 * morning, with a connection or without. Scheduled by
 * [SyncScheduler.schedulePlansRefresh]; runs only with a connection.
 */
class PlansRefreshWorker(
    appContext: Context,
    params: WorkerParameters,
) : CoroutineWorker(appContext, params) {

    override suspend fun doWork(): Result {
        val snapshot = Settings(applicationContext).snapshot()
        if (!snapshot.isConfigured) return Result.success()

        return try {
            SavedPlans(applicationContext).refresh(
                TasksClient.build(snapshot.serverUrl, snapshot.apiToken),
                SavedPlans.account(snapshot.serverUrl, snapshot.apiToken),
                LocalDate.now(),
            )
            Result.success()
        } catch (t: Throwable) {
            Result.retry()
        }
    }
}
