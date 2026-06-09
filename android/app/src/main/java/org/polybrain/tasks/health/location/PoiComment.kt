package org.polybrain.tasks.health.location

import java.util.Locale

/**
 * Compose a journal comment from an optional location [fix] and the user's
 * [text]. When a fix is present, a leading `#poi lat=… lng=…` line is prepended
 * (the backend parses it into a HabitTracked); otherwise the trimmed text is
 * used as-is. Shared by trip notes/photos and standalone photos so the marker
 * format stays identical across all of them.
 */
fun composeComment(fix: LocationFix?, text: String): String {
    val trimmed = text.trim()
    return if (fix != null) {
        val prefix = String.format(
            Locale.US, "#poi lat=%.6f lng=%.6f", fix.lat, fix.lng,
        )
        if (trimmed.isEmpty()) prefix else "$prefix\n$trimmed"
    } else {
        trimmed
    }
}
