package org.polybrain.tasks.health.location

import kotlin.math.abs
import kotlin.math.asin
import kotlin.math.cos
import kotlin.math.min
import kotlin.math.pow
import kotlin.math.sin
import kotlin.math.sqrt
import org.polybrain.tasks.health.data.Breadcrumb

/**
 * Derives a photo's location from a trip's breadcrumb trail, by the photo's
 * capture time — so you can curate/upload photos long after (and far from)
 * where they were taken and still attach the right coordinates.
 *
 * Rule (see plan): take the breadcrumbs immediately before and after the
 * capture time.
 *  - If the nearer one is within [DIRECT_MATCH_MS] → use it (direct hit).
 *  - Otherwise the capture time sits in a tracking gap; only trust it if it is
 *    bracketed by two points less than [STATIONARY_METERS] apart (you were in
 *    one place) and use the closer-in-time one. Never interpolate across a
 *    move — return null so the caller sends the photo without a location.
 */
object PhotoLocationResolver {

    private const val DIRECT_MATCH_MS = 2 * 60 * 1000L
    private const val STATIONARY_METERS = 200.0

    fun resolve(breadcrumbs: List<Breadcrumb>, captureMs: Long): LocationFix? {
        if (breadcrumbs.isEmpty()) return null

        val before = breadcrumbs.filter { it.t <= captureMs }.maxByOrNull { it.t }
        val after = breadcrumbs.filter { it.t >= captureMs }.minByOrNull { it.t }
        val nearest = closer(before, after, captureMs)

        if (nearest != null && abs(nearest.t - captureMs) <= DIRECT_MATCH_MS) {
            return nearest.toFix()
        }

        // In a >2 min gap: only trust a bracket of two nearby points.
        if (before != null && after != null &&
            haversineMeters(before.lat, before.lng, after.lat, after.lng) < STATIONARY_METERS
        ) {
            return closer(before, after, captureMs)!!.toFix()
        }

        return null
    }

    private fun closer(a: Breadcrumb?, b: Breadcrumb?, t: Long): Breadcrumb? {
        if (a == null) return b
        if (b == null) return a
        return if (abs(a.t - t) <= abs(b.t - t)) a else b
    }

    private fun Breadcrumb.toFix() = LocationFix(lat = lat, lng = lng, accuracyMeters = acc)

    /** Great-circle distance in metres between two lat/lng points. */
    fun haversineMeters(lat1: Double, lng1: Double, lat2: Double, lng2: Double): Double {
        val earthRadius = 6_371_000.0
        val dLat = Math.toRadians(lat2 - lat1)
        val dLng = Math.toRadians(lng2 - lng1)
        val a = sin(dLat / 2).pow(2) +
            cos(Math.toRadians(lat1)) * cos(Math.toRadians(lat2)) * sin(dLng / 2).pow(2)
        return 2 * earthRadius * asin(min(1.0, sqrt(a)))
    }
}
