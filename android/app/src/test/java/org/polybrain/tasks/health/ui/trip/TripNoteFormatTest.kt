package org.polybrain.tasks.health.ui.trip

import java.time.ZoneId
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class TripNoteFormatTest {

    private val utc: ZoneId = ZoneId.of("UTC")

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

    // --- formatTripRange ---------------------------------------------------

    @Test
    fun `active trip range shows only the start datetime`() {
        val s = formatTripRange(
            startedIso = "2026-05-25T10:00:00Z",
            stoppedIso = null,
            zone = utc,
        )
        assertEquals("2026-05-25 10:00", s)
    }

    @Test
    fun `single-day completed trip omits the date on the end side`() {
        val s = formatTripRange(
            startedIso = "2026-05-25T10:00:00Z",
            stoppedIso = "2026-05-25T18:30:00Z",
            zone = utc,
        )
        assertEquals("2026-05-25 10:00 → 18:30", s)
    }

    @Test
    fun `multi-day completed trip repeats the date on both sides`() {
        val s = formatTripRange(
            startedIso = "2026-05-25T22:00:00Z",
            stoppedIso = "2026-05-27T03:15:00Z",
            zone = utc,
        )
        assertEquals("2026-05-25 22:00 → 2026-05-27 03:15", s)
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
