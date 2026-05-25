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

data class PoiCoords(val lat: Double, val lng: Double)

data class ParsedTripNote(
    /** Comment body with the leading "#poi lat=… lng=…" line removed. */
    val text: String,
    /** Coordinates from that line, or null if no leading POI marker. */
    val poi: PoiCoords?,
)

/**
 * Strip a leading `#poi lat=<float> lng=<float>` line from a trip note
 * and surface the coordinates separately so the UI can offer an
 * "Open in Maps" action.
 *
 * Only the **first** line is examined — that's where the Android
 * client always writes the auto-prepended POI marker. POI markers
 * embedded mid-comment are intentionally left in the displayed text
 * (they're user-typed in that case and probably meant to be read).
 */
private val POI_LINE_RE = Regex(
    """^\s*#poi\s+lat=(-?\d+(?:\.\d+)?)\s+lng=(-?\d+(?:\.\d+)?)(?:\s+[^\n]*)?(?:\n|$)"""
)

fun parseTripNote(comment: String): ParsedTripNote {
    val match = POI_LINE_RE.find(comment) ?: return ParsedTripNote(comment, null)
    val lat = match.groupValues[1].toDoubleOrNull()
    val lng = match.groupValues[2].toDoubleOrNull()
    if (lat == null || lng == null) return ParsedTripNote(comment, null)
    val stripped = comment.substring(match.range.last + 1)
    return ParsedTripNote(stripped.trimStart('\n').trimEnd(), PoiCoords(lat, lng))
}

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

private fun parseAsLocalDate(iso: String, zone: ZoneId): LocalDate =
    OffsetDateTime.parse(iso).atZoneSameInstant(zone).toLocalDate()

/**
 * Fires an ACTION_VIEW intent with a `geo:` URI so the user's Maps
 * app (Google Maps, OsmAnd, Organic Maps, …) opens the coordinates
 * with a pin dropped. Silently no-ops if no app can handle the URI.
 */
fun openPoiInMaps(context: Context, poi: PoiCoords) {
    val coords = String.format(Locale.US, "%f,%f", poi.lat, poi.lng)
    val uri = Uri.parse("geo:$coords?q=$coords")
    val intent = Intent(Intent.ACTION_VIEW, uri)
    try {
        context.startActivity(intent)
    } catch (_: ActivityNotFoundException) {
        // No installed app handles geo URIs. Nothing reasonable to do
        // beyond ignoring the tap; a Toast would be intrusive here.
    }
}
