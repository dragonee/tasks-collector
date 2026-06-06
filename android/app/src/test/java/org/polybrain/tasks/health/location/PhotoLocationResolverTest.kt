package org.polybrain.tasks.health.location

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Test
import org.polybrain.tasks.health.data.Breadcrumb

class PhotoLocationResolverTest {

    private val min = 60_000L

    @Test
    fun `empty trail yields no location`() {
        assertNull(PhotoLocationResolver.resolve(emptyList(), 1_000))
    }

    @Test
    fun `direct hit within two minutes uses the nearest point`() {
        val crumbs = listOf(
            Breadcrumb(t = 0, lat = 10.0, lng = 10.0),
            Breadcrumb(t = 1 * min, lat = 20.0, lng = 20.0), // 1 min before capture
            Breadcrumb(t = 5 * min, lat = 50.0, lng = 50.0),
        )
        val fix = PhotoLocationResolver.resolve(crumbs, 2 * min)
        assertNotNull(fix)
        // Nearest to t=2min is the t=1min point (1 min away) vs t=5min (3 min).
        assertEquals(20.0, fix!!.lat, 0.0)
        assertEquals(20.0, fix.lng, 0.0)
    }

    @Test
    fun `gap bracketed by nearby points uses the closer one in time`() {
        // No point within 2 min of capture, but before/after are ~110 m apart
        // (same place) → stationary, use closer-in-time (the after point).
        val crumbs = listOf(
            Breadcrumb(t = 0, lat = 52.230000, lng = 21.010000), // 10 min before
            Breadcrumb(t = 13 * min, lat = 52.231000, lng = 21.010000), // 3 min after
        )
        val fix = PhotoLocationResolver.resolve(crumbs, 10 * min)
        assertNotNull(fix)
        assertEquals(52.231000, fix!!.lat, 0.0) // the after point is closer in time
    }

    @Test
    fun `gap bracketed by far apart points yields no location`() {
        // before/after are kilometres apart → you were moving → don't guess.
        val crumbs = listOf(
            Breadcrumb(t = 0, lat = 52.2300, lng = 21.0100),
            Breadcrumb(t = 20 * min, lat = 52.4000, lng = 21.0100), // ~19 km away
        )
        assertNull(PhotoLocationResolver.resolve(crumbs, 10 * min))
    }

    @Test
    fun `only one side in a gap yields no location`() {
        // Photo taken well after the last breadcrumb (tracking ended) — no
        // bracketing pair to confirm a stationary position.
        val crumbs = listOf(
            Breadcrumb(t = 0, lat = 10.0, lng = 10.0),
            Breadcrumb(t = 5 * min, lat = 10.0, lng = 10.0),
        )
        assertNull(PhotoLocationResolver.resolve(crumbs, 30 * min))
    }

    @Test
    fun `exact timestamp match is a direct hit`() {
        val crumbs = listOf(Breadcrumb(t = 7 * min, lat = 1.0, lng = 2.0, acc = 9f))
        val fix = PhotoLocationResolver.resolve(crumbs, 7 * min)
        assertNotNull(fix)
        assertEquals(1.0, fix!!.lat, 0.0)
        assertEquals(9f, fix.accuracyMeters)
    }

    @Test
    fun `haversine matches a known city-scale distance`() {
        // Warsaw city center to ~1 km north (≈0.009 deg latitude).
        val d = PhotoLocationResolver.haversineMeters(52.2297, 21.0122, 52.2387, 21.0122)
        assertEquals(1000.0, d, 5.0)
    }
}
