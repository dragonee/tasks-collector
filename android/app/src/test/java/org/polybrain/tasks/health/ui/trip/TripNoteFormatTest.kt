package org.polybrain.tasks.health.ui.trip

import java.time.ZoneId
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class TripNoteFormatTest {

    private val utc: ZoneId = ZoneId.of("UTC")

    // --- parseTripNote ------------------------------------------------------

    @Test
    fun `parses leading poi line and strips it from text`() {
        val parsed = parseTripNote("#poi lat=40.7128 lng=-74.0060\nCoffee at the corner")
        assertEquals("Coffee at the corner", parsed.text)
        assertNotNull(parsed.poi)
        assertEquals(40.7128, parsed.poi!!.lat, 0.0)
        assertEquals(-74.0060, parsed.poi!!.lng, 0.0)
    }

    @Test
    fun `parses poi line on its own with no body`() {
        val parsed = parseTripNote("#poi lat=10.0 lng=20.0")
        assertEquals("", parsed.text)
        assertNotNull(parsed.poi)
    }

    @Test
    fun `leaves comment alone when no poi line is present`() {
        val parsed = parseTripNote("Plain note without coordinates")
        assertEquals("Plain note without coordinates", parsed.text)
        assertNull(parsed.poi)
    }

    @Test
    fun `does not strip poi mention from inside the body`() {
        val parsed = parseTripNote("Saw a #poi sign here\nbut no coords")
        assertEquals("Saw a #poi sign here\nbut no coords", parsed.text)
        assertNull(parsed.poi)
    }

    @Test
    fun `accepts negative coordinates`() {
        val parsed = parseTripNote("#poi lat=-33.8688 lng=151.2093\nSydney")
        assertEquals(-33.8688, parsed.poi!!.lat, 0.0)
        assertEquals(151.2093, parsed.poi!!.lng, 0.0)
    }

    @Test
    fun `preserves multi-line body verbatim`() {
        val parsed = parseTripNote(
            "#poi lat=1 lng=2\nFirst line\n\nThird line  with trailing  "
        )
        assertEquals("First line\n\nThird line  with trailing  ", parsed.text)
    }

    @Test
    fun `tolerates extra text on the poi line itself`() {
        // A future client may append accuracy/altitude/labels on the same
        // line; the body still starts on the next line.
        val parsed = parseTripNote(
            "#poi lat=10 lng=20 acc=5\nThe note body stays whole"
        )
        assertEquals("The note body stays whole", parsed.text)
        assertEquals(10.0, parsed.poi!!.lat, 0.0)
        assertEquals(20.0, parsed.poi!!.lng, 0.0)
    }

    // --- pickEventFormatter -------------------------------------------------

    @Test
    fun `single-day trip uses HH-mm pattern`() {
        val formatter = pickEventFormatter(
            startedIso = "2026-05-25T10:00:00Z",
            stoppedIso = "2026-05-25T18:00:00Z",
            eventIsos = listOf("2026-05-25T11:00:00Z", "2026-05-25T17:30:00Z"),
            zone = utc,
        )
        assertEquals("11:00", formatInstant("2026-05-25T11:00:00Z", formatter))
        // The formatter should NOT include a date component.
        assertTrue(!formatInstant("2026-05-25T17:30:00Z", formatter).contains("-"))
    }

    @Test
    fun `multi-day trip uses full date-time pattern`() {
        val formatter = pickEventFormatter(
            startedIso = "2026-05-25T10:00:00Z",
            stoppedIso = "2026-05-27T18:00:00Z",
            eventIsos = listOf("2026-05-25T11:00:00Z", "2026-05-26T14:00:00Z"),
            zone = utc,
        )
        assertEquals("2026-05-26 14:00", formatInstant("2026-05-26T14:00:00Z", formatter))
    }

    @Test
    fun `active trip with no stopped still picks single-day when events fit`() {
        val formatter = pickEventFormatter(
            startedIso = "2026-05-25T08:00:00Z",
            stoppedIso = null,
            eventIsos = listOf("2026-05-25T12:00:00Z"),
            zone = utc,
        )
        assertEquals("12:00", formatInstant("2026-05-25T12:00:00Z", formatter))
    }

    @Test
    fun `active trip spanning into a new day flips to full date-time`() {
        val formatter = pickEventFormatter(
            startedIso = "2026-05-25T22:00:00Z",
            stoppedIso = null,
            eventIsos = listOf(
                "2026-05-25T23:00:00Z",
                "2026-05-26T01:00:00Z",
            ),
            zone = utc,
        )
        assertEquals(
            "2026-05-25 23:00",
            formatInstant("2026-05-25T23:00:00Z", formatter)
        )
        assertEquals(
            "2026-05-26 01:00",
            formatInstant("2026-05-26T01:00:00Z", formatter)
        )
    }
}
