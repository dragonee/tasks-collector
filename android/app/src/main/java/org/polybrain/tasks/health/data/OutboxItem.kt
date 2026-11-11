package org.polybrain.tasks.health.data

import kotlinx.serialization.Serializable

/**
 * One queued write awaiting delivery to the server: a trip note, a photo, or
 * something done to a task ([task]).
 *
 * Everything needed to send is frozen at enqueue time so the entry survives an
 * offline period, an app kill, or a reboot: the [comment] already carries the
 * `#poi lat=… lng=…` line (so the GPS fix is captured even with no network),
 * [published] is the moment the user acted (not the moment of eventual upload),
 * and for photos the bytes are copied into the outbox dir ([photoFile]) because
 * the picker's content `Uri` is only readable for the current session.
 *
 * [id] doubles as the server `idempotency_key`, so a retry whose first response
 * was lost re-uses the existing event instead of creating a duplicate.
 *
 * [storyId] is null for a standalone photo (a `PhotoTaken` with no trip): the
 * drainer then delivers it through the storyless photo endpoints instead of the
 * trip ones, and [forStory] never returns it.
 *
 * A task call ([Kind.TASK]) has no story and no comment of its own: what it
 * does is in [task], and [published] is the moment of the tap.
 */
@Serializable
data class OutboxItem(
    val id: String,
    val kind: Kind,
    val storyId: Long?,
    val comment: String,
    val published: String,
    val createdAt: Long,
    // Photos only:
    val contentType: String? = null,
    val photoFile: String? = null,
    // Hex SHA-256 of the photo bytes. Sent to the trip confirm endpoint as
    // `content_hash` so the server dedups the same image within a trip, and
    // used locally to skip enqueuing a photo already queued (see Outbox).
    val contentHash: String? = null,
    // Photo resume guards: set together only after a successful S3 PUT, so a
    // confirm-failure retry skips straight to confirm and never re-uploads.
    val presignedKey: String? = null,
    val uploaded: Boolean = false,
    // Task calls only: what to do, to which task. The drainer writes the
    // task's id back here once it knows it, so a retry names the same task.
    val task: TaskOp? = null,
    // Delivery bookkeeping, surfaced in the timeline.
    val attempts: Int = 0,
    val lastError: String? = null,
    // A 4xx the worker won't auto-retry (e.g. trip stopped); kept visible so
    // the user can manually retry or discard.
    val failedPermanently: Boolean = false,
) {
    enum class Kind { NOTE, PHOTO, TASK }

    val isPhoto: Boolean get() = kind == Kind.PHOTO

    val isTask: Boolean get() = kind == Kind.TASK
}
