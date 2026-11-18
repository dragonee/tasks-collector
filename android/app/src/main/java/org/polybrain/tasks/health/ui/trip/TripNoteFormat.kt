package org.polybrain.tasks.health.ui.trip

import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.net.Uri
import java.time.LocalDate
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale

/**
 * Picks a `DateTimeFormatter` for showing event timestamps inside a
 * trip detail. Returns ``HH:mm`` when every relevant timestamp (the
 * trip's started/stopped and every event) falls on the same local
 * calendar date; ``yyyy-MM-dd HH:mm`` otherwise so multi-day trips
 * don't look like a wall of duplicate clock times.
 */
fun pickEventFormatter(
    startedIso: String,
    stoppedIso: String?,
    eventIsos: List<String>,
    zone: ZoneId = ZoneId.systemDefault(),
): DateTimeFormatter {
    val dates: Set<LocalDate> = buildSet {
        add(parseAsLocalDate(startedIso, zone))
        stoppedIso?.let { add(parseAsLocalDate(it, zone)) }
        eventIsos.forEach { add(parseAsLocalDate(it, zone)) }
    }
    val pattern = if (dates.size <= 1) "HH:mm" else "yyyy-MM-dd HH:mm"
    return DateTimeFormatter.ofPattern(pattern, Locale.US).withZone(zone)
}

fun formatInstant(iso: String, formatter: DateTimeFormatter): String =
    OffsetDateTime.parse(iso).toInstant().let(formatter::format)

/**
 * Formats a trip's started → stopped range for display in the Trips
 * list. The start always carries a full date so rows are
 * self-describing in a scrolling list; the end side drops the date if
 * the trip ended on the same calendar day. Active trips (no stop)
 * render as just the start datetime.
 */
fun formatTripRange(
    startedIso: String,
    stoppedIso: String?,
    zone: ZoneId = ZoneId.systemDefault(),
): String {
    val dateTime = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm", Locale.US).withZone(zone)
    val time = DateTimeFormatter.ofPattern("HH:mm", Locale.US).withZone(zone)

    val started = OffsetDateTime.parse(startedIso)
    val startStr = dateTime.format(started.toInstant())
    if (stoppedIso == null) return startStr

    val stopped = OffsetDateTime.parse(stoppedIso)
    val sameDay = started.atZoneSameInstant(zone).toLocalDate() ==
            stopped.atZoneSameInstant(zone).toLocalDate()
    val endStr = if (sameDay) time.format(stopped.toInstant())
                 else dateTime.format(stopped.toInstant())
    return "$startStr → $endStr"
}

private fun parseAsLocalDate(iso: String, zone: ZoneId): LocalDate =
    OffsetDateTime.parse(iso).atZoneSameInstant(zone).toLocalDate()

/**
 * Fires an ACTION_VIEW intent with a `geo:` URI so the user's Maps
 * app (Google Maps, OsmAnd, Organic Maps, …) opens the coordinates
 * with a pin dropped. Silently no-ops if no app can handle the URI.
 */
fun openInMaps(context: Context, lat: Double, lng: Double) {
    val coords = String.format(Locale.US, "%f,%f", lat, lng)
    val uri = Uri.parse("geo:$coords?q=$coords")
    val intent = Intent(Intent.ACTION_VIEW, uri)
    try {
        context.startActivity(intent)
    } catch (_: ActivityNotFoundException) {
        // No installed app handles geo URIs. Nothing reasonable to do
        // beyond ignoring the tap; a Toast would be intrusive here.
    }
}
