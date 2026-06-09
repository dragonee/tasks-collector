package org.polybrain.tasks.health.ui.photo

import android.content.ContentResolver
import android.net.Uri
import android.provider.MediaStore
import java.time.Instant
import java.time.OffsetDateTime
import java.time.ZoneId

/**
 * The gallery's `DATE_TAKEN` (epoch millis, UTC) for a picked image, or null
 * when absent. Shared by the trip-photo and standalone-photo flows.
 */
fun captureMillisFor(resolver: ContentResolver, uri: Uri): Long? =
    runCatching {
        resolver.query(
            uri,
            arrayOf(MediaStore.Images.Media.DATE_TAKEN),
            null,
            null,
            null,
        )?.use { cursor ->
            val index = cursor.getColumnIndex(MediaStore.Images.Media.DATE_TAKEN)
            if (index >= 0 && cursor.moveToFirst() && !cursor.isNull(index)) {
                cursor.getLong(index)
            } else {
                null
            }
        }
    }.getOrNull()?.takeIf { it > 0 }

/**
 * Best-effort ISO-8601 capture time of a picked image: the gallery's
 * `DATE_TAKEN` when present, else now. The backend overrides this with the
 * original's EXIF `DateTimeOriginal` when the file carries one.
 */
fun captureTimeFor(resolver: ContentResolver, uri: Uri): String {
    val millis = captureMillisFor(resolver, uri)
    return if (millis != null) {
        OffsetDateTime.ofInstant(
            Instant.ofEpochMilli(millis),
            ZoneId.systemDefault(),
        ).toString()
    } else {
        OffsetDateTime.now().toString()
    }
}
