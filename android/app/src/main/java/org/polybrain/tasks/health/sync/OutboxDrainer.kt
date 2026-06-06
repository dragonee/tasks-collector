package org.polybrain.tasks.health.sync

import java.io.IOException
import org.polybrain.tasks.health.data.Outbox
import org.polybrain.tasks.health.data.OutboxItem
import org.polybrain.tasks.health.data.PhotoConfirmRequest
import org.polybrain.tasks.health.data.PhotoPresignRequest
import org.polybrain.tasks.health.data.TasksApi
import org.polybrain.tasks.health.data.TripNoteRequest
import retrofit2.HttpException

/**
 * Pure per-item delivery logic, factored out of [OutboxWorker] so it can be
 * unit-tested with a fake [TasksApi] and PUT function (no Android, no network).
 *
 * Each item's [OutboxItem.id] is sent as the server `idempotency_key`, so a
 * retry after a lost response is exactly-once.
 */
object OutboxDrainer {

    /** Result of attempting to deliver one item; carries the latest item state. */
    sealed class Outcome {
        abstract val item: OutboxItem

        /** Delivered — caller should remove the item. */
        data class Sent(override val item: OutboxItem) : Outcome()

        /** Transient failure (network / 5xx / 401 / 429) — keep and retry later. */
        data class Retry(override val item: OutboxItem, val error: String) : Outcome()

        /** Permanent failure (4xx) — keep but stop auto-retrying; surface to the user. */
        data class Permanent(override val item: OutboxItem, val error: String) : Outcome()
    }

    /** Abstracts the raw S3 PUT so tests don't hit the network. Throws on failure. */
    fun interface PhotoPutter {
        fun put(url: String, bytes: ByteArray, contentType: String)
    }

    /** Thrown for unrecoverable problems that should not be retried. */
    private class PermanentFailure(message: String) : Exception(message)

    suspend fun process(
        item: OutboxItem,
        api: TasksApi,
        outbox: Outbox,
        put: PhotoPutter,
    ): Outcome {
        var current = item
        return try {
            when (item.kind) {
                OutboxItem.Kind.NOTE -> {
                    api.addTripNote(
                        TripNoteRequest(
                            storyId = item.storyId,
                            comment = item.comment,
                            published = item.published,
                            idempotencyKey = item.id,
                        )
                    )
                }
                OutboxItem.Kind.PHOTO -> {
                    current = sendPhoto(current, api, outbox, put)
                }
            }
            Outcome.Sent(current)
        } catch (e: PermanentFailure) {
            Outcome.Permanent(current, e.message ?: "permanent failure")
        } catch (e: HttpException) {
            val msg = "HTTP ${e.code()}"
            if (isRetryable(e.code())) Outcome.Retry(current, msg)
            else Outcome.Permanent(current, msg)
        } catch (e: IOException) {
            Outcome.Retry(current, e.message ?: "network error")
        } catch (e: Throwable) {
            // Unexpected (e.g. malformed response) — don't spin forever on it.
            Outcome.Permanent(current, e.message ?: e.javaClass.simpleName)
        }
    }

    /**
     * Presign → PUT → confirm, resumable. The `uploaded`/`presignedKey` pair is
     * persisted only *after* a successful PUT, so a confirm-failure retry skips
     * straight to confirm and a PUT-failure retry re-presigns fresh. Returns the
     * (possibly updated) item so the caller's bookkeeping won't clobber the
     * resume flags.
     */
    private suspend fun sendPhoto(
        item: OutboxItem,
        api: TasksApi,
        outbox: Outbox,
        put: PhotoPutter,
    ): OutboxItem {
        var current = item
        val contentType = current.contentType ?: "image/jpeg"
        if (!current.uploaded) {
            val bytes = outbox.photoBytes(current)
                ?: throw PermanentFailure("photo file missing for ${current.id}")
            val presign = api.presignPhoto(
                PhotoPresignRequest(storyId = current.storyId, contentType = contentType)
            )
            put.put(presign.uploadUrl, bytes, contentType)
            // Persist immediately so a process kill after PUT still resumes at confirm.
            current = current.copy(presignedKey = presign.key, uploaded = true)
            outbox.update(current)
        }
        api.addTripPhoto(
            PhotoConfirmRequest(
                storyId = current.storyId,
                key = current.presignedKey!!,
                comment = current.comment,
                contentType = contentType,
                published = current.published,
                idempotencyKey = current.id,
            )
        )
        return current
    }

    /** 401/408/429 and 5xx are worth retrying; other 4xx are permanent. */
    private fun isRetryable(code: Int): Boolean =
        code == 401 || code == 408 || code == 429 || code >= 500
}
