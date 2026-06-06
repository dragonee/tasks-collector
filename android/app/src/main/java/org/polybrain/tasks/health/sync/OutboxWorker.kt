package org.polybrain.tasks.health.sync

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import org.polybrain.tasks.health.data.Outbox
import org.polybrain.tasks.health.data.Settings
import org.polybrain.tasks.health.data.TasksClient

/**
 * Drains the [Outbox] queue: delivers each pending trip note/photo to the
 * server, retrying transient failures. Scheduled with a network constraint by
 * [SyncScheduler.drainOutbox], so it only runs when connectivity is available
 * and WorkManager re-runs it (with backoff) after a [androidx.work.ListenableWorker.Result.retry].
 */
class OutboxWorker(
    appContext: Context,
    params: WorkerParameters,
) : CoroutineWorker(appContext, params) {

    private val settings = Settings(applicationContext)
    private val outbox = Outbox(applicationContext)

    override suspend fun doWork(): Result {
        val snapshot = settings.snapshot()
        // Nothing we can do without a server/token; leave items queued for a
        // later trigger (a save in Settings re-kicks the drain).
        if (!snapshot.isConfigured) return Result.success()

        val api = TasksClient.build(snapshot.serverUrl, snapshot.apiToken)
        val put = OutboxDrainer.PhotoPutter { url, bytes, contentType ->
            TasksClient.putToPresignedUrl(url, bytes, contentType)
        }

        var hadRetryable = false
        for (item in outbox.all()) {
            if (item.failedPermanently) continue
            when (val outcome = OutboxDrainer.process(item, api, outbox, put)) {
                is OutboxDrainer.Outcome.Sent -> outbox.remove(outcome.item)
                is OutboxDrainer.Outcome.Retry -> {
                    outbox.update(
                        outcome.item.copy(
                            attempts = outcome.item.attempts + 1,
                            lastError = outcome.error,
                        )
                    )
                    hadRetryable = true
                }
                is OutboxDrainer.Outcome.Permanent -> outbox.update(
                    outcome.item.copy(
                        attempts = outcome.item.attempts + 1,
                        lastError = outcome.error,
                        failedPermanently = true,
                    )
                )
            }
        }

        // Ask WorkManager to re-run (with exponential backoff) while anything
        // still needs delivery; otherwise we're done.
        return if (hadRetryable) Result.retry() else Result.success()
    }
}
