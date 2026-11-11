package org.polybrain.tasks.health.sync

import java.io.IOException
import org.polybrain.tasks.health.data.Outbox
import org.polybrain.tasks.health.data.OutboxItem
import org.polybrain.tasks.health.data.PhotoConfirmRequest
import org.polybrain.tasks.health.data.PhotoPresignRequest
import org.polybrain.tasks.health.data.PlanItemRequest
import org.polybrain.tasks.health.data.PlanRef
import org.polybrain.tasks.health.data.PlanTextRequest
import org.polybrain.tasks.health.data.StandalonePhotoConfirmRequest
import org.polybrain.tasks.health.data.StandalonePhotoPresignRequest
import org.polybrain.tasks.health.data.TaskCompleteRequest
import org.polybrain.tasks.health.data.TaskMoveRequest
import org.polybrain.tasks.health.data.TaskOp
import org.polybrain.tasks.health.data.TaskReopenRequest
import org.polybrain.tasks.health.data.TasksApi
import org.polybrain.tasks.health.data.TripNoteRequest
import retrofit2.HttpException

/**
 * Pure delivery logic, factored out of [OutboxWorker] so it can be
 * unit-tested with a fake [TasksApi] and PUT function (no Android, no network).
 *
 * Each item's [OutboxItem.id] is sent as the server `idempotency_key`, so a
 * retry after a lost response is exactly-once. Task calls that take no key
 * are ones the server answers the same way twice (see [sendTask]).
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

    /**
     * One pass over the queue: deliver what can be delivered and record on
     * each item what became of it. Returns whether anything is left to retry.
     *
     * Task calls go first: they are small, and a tick should not wait behind
     * a photo upload (they don't depend on trip writes). Among themselves
     * they keep their order — a tick, then its untick — so one that has to
     * wait holds back those queued after it.
     */
    suspend fun drain(outbox: Outbox, api: TasksApi, put: PhotoPutter): Boolean {
        val queued = outbox.all().filterNot { it.failedPermanently }
        var hadRetryable = false
        var tasksHeld = false
        for (item in queued.filter { it.isTask } + queued.filterNot { it.isTask }) {
            if (item.isTask && tasksHeld) continue
            when (val outcome = process(item, api, outbox, put)) {
                is Outcome.Sent -> outbox.remove(outcome.item)
                is Outcome.Retry -> {
                    outbox.update(
                        outcome.item.copy(
                            attempts = outcome.item.attempts + 1,
                            lastError = outcome.error,
                        )
                    )
                    hadRetryable = true
                    tasksHeld = tasksHeld || item.isTask
                }
                is Outcome.Permanent -> outbox.update(
                    outcome.item.copy(
                        attempts = outcome.item.attempts + 1,
                        lastError = outcome.error,
                        failedPermanently = true,
                    )
                )
            }
        }
        return hadRetryable
    }

    suspend fun process(
        item: OutboxItem,
        api: TasksApi,
        outbox: Outbox,
        put: PhotoPutter,
    ): Outcome {
        var current = item

        // What an item learns on the way (a photo is uploaded, a task's id is
        // known) is kept through this, so that a failure further on reports
        // the item as it is now and the bookkeeping doesn't write the old
        // one back over it.
        fun save(updated: OutboxItem) {
            current = updated
            outbox.update(updated)
        }

        return try {
            when (item.kind) {
                OutboxItem.Kind.NOTE -> {
                    // Notes are always trip-bound; a storyless note is a bug.
                    api.addTripNote(
                        TripNoteRequest(
                            storyId = requireNotNull(item.storyId) {
                                "note ${item.id} has no story"
                            },
                            comment = item.comment,
                            published = item.published,
                            idempotencyKey = item.id,
                        )
                    )
                }
                OutboxItem.Kind.PHOTO -> sendPhoto(item, api, outbox, put, ::save)
                OutboxItem.Kind.TASK -> sendTask(item, api, ::save)
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
     * straight to confirm and a PUT-failure retry re-presigns fresh.
     *
     * A null [OutboxItem.storyId] is a standalone photo (no trip): it goes
     * through the storyless `photo/…` endpoints instead of the trip ones. The
     * resume logic is identical for both — only the two API calls differ.
     */
    private suspend fun sendPhoto(
        item: OutboxItem,
        api: TasksApi,
        outbox: Outbox,
        put: PhotoPutter,
        save: (OutboxItem) -> Unit,
    ) {
        var current = item
        val contentType = current.contentType ?: "image/jpeg"
        val storyId = current.storyId
        if (!current.uploaded) {
            val bytes = outbox.photoBytes(current)
                ?: throw PermanentFailure("photo file missing for ${current.id}")
            val presign = if (storyId != null) {
                api.presignPhoto(
                    PhotoPresignRequest(storyId = storyId, contentType = contentType)
                )
            } else {
                api.presignStandalonePhoto(
                    StandalonePhotoPresignRequest(contentType = contentType)
                )
            }
            put.put(presign.uploadUrl, bytes, contentType)
            // Persist immediately so a process kill after PUT still resumes at confirm.
            current = current.copy(presignedKey = presign.key, uploaded = true)
            save(current)
        }
        val key = current.presignedKey!!
        if (storyId != null) {
            api.addTripPhoto(
                PhotoConfirmRequest(
                    storyId = storyId,
                    key = key,
                    comment = current.comment,
                    contentType = contentType,
                    published = current.published,
                    idempotencyKey = current.id,
                    contentHash = current.contentHash,
                )
            )
        } else {
            api.addStandalonePhoto(
                StandalonePhotoConfirmRequest(
                    key = key,
                    comment = current.comment,
                    contentType = contentType,
                    published = current.published,
                    idempotencyKey = current.id,
                )
            )
        }
    }

    /**
     * Make the call a task item stands for. Sent again after a lost answer,
     * each call leaves things as the first one did: planning a task that is
     * on the plan changes nothing, a completion carries the item's id as its
     * idempotency key, and a step is taken back only from the count the user
     * saw.
     *
     * A task without an id (a plain line of a plan, a task typed in before
     * this) is named by its text on the plan of the day: planning it there
     * gives the id. The id is written to the item before it is used, so a
     * retry names the same task even when the call has moved it off that
     * plan.
     */
    private suspend fun sendTask(item: OutboxItem, api: TasksApi, save: (OutboxItem) -> Unit) {
        val op = item.task ?: throw PermanentFailure("task item ${item.id} says nothing to do")

        suspend fun id(): String {
            op.task.id?.let { return it }
            val planned = api.planText(PlanTextRequest(op.task.text, op.date)).id
                ?: throw PermanentFailure("the server gave no id for \"${op.task.text}\"")
            save(item.copy(task = op.copy(task = op.task.copy(id = planned))))
            return planned
        }

        when (op.type) {
            TaskOp.Type.PLAN -> {
                val known = op.task.id
                if (known == null) {
                    api.planText(PlanTextRequest(op.task.text, op.date))
                } else {
                    api.planTask(known, PlanRef(op.date))
                }
            }
            TaskOp.Type.PLAN_ITEM -> api.planItem(
                PlanItemRequest(
                    boardId = op.boardId ?: throw PermanentFailure("no board for ${item.id}"),
                    itemId = op.itemId ?: throw PermanentFailure("no board item for ${item.id}"),
                    date = op.date,
                )
            )
            TaskOp.Type.COMPLETE -> api.completeTask(
                id(),
                TaskCompleteRequest(
                    day = op.date,
                    at = item.published,
                    note = op.note,
                    storyId = op.storyId,
                    idempotencyKey = item.id,
                ),
            )
            TaskOp.Type.REOPEN -> api.reopenTask(
                id(),
                TaskReopenRequest(doneCount = op.task.doneCount.takeIf { it > 0 }),
            )
            TaskOp.Type.MOVE -> api.moveTask(
                id(),
                TaskMoveRequest(
                    fromDate = op.date,
                    toDate = op.toDate ?: throw PermanentFailure("no day to move ${item.id} to"),
                ),
            )
            TaskOp.Type.UNPLAN -> {
                // Response<Unit> does not throw on an HTTP error. A 404 is a
                // task that is gone, as one nothing remembers is once it is
                // off its last plan: the answer to this call sent again.
                val response = api.unplanTask(id(), PlanRef(op.date))
                if (!response.isSuccessful && response.code() != 404) {
                    throw HttpException(response)
                }
            }
        }
    }

    /** 401/408/429 and 5xx are worth retrying; other 4xx are permanent. */
    private fun isRetryable(code: Int): Boolean =
        code == 401 || code == 408 || code == 429 || code >= 500
}
