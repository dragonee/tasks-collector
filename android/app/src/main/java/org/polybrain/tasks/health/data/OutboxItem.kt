package org.polybrain.tasks.health.data

import kotlinx.serialization.Serializable

/**
 * One queued trip write awaiting delivery to the server.
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
    // Photo resume guards: set together only after a successful S3 PUT, so a
    // confirm-failure retry skips straight to confirm and never re-uploads.
    val presignedKey: String? = null,
    val uploaded: Boolean = false,
    // Delivery bookkeeping, surfaced in the timeline.
    val attempts: Int = 0,
    val lastError: String? = null,
    // A 4xx the worker won't auto-retry (e.g. trip stopped); kept visible so
    // the user can manually retry or discard.
    val failedPermanently: Boolean = false,
) {
    enum class Kind { NOTE, PHOTO }

    val isPhoto: Boolean get() = kind == Kind.PHOTO
}
