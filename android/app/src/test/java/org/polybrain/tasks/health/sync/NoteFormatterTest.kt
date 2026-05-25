package org.polybrain.tasks.health.sync

import org.polybrain.tasks.health.data.DailyMetrics
import java.time.LocalDate
import org.junit.Assert.assertEquals
import org.junit.Test

class NoteFormatterTest {

    private val anyDate: LocalDate = LocalDate.of(2026, 5, 17)

    @Test
    fun `formats all four metrics`() {
        val note = NoteFormatter.format(
            DailyMetrics(
                date = anyDate,
                steps = 8520,
                distanceMeters = 6234.5,
                activeMinutes = 42,
                kcal = 1499.4,
            )
        )
        assertEquals("steps=8520 distance=6.2km active=42min kcal=1499", note)
    }

    @Test
    fun `zero metrics still render with zero values`() {
        val note = NoteFormatter.format(
            DailyMetrics(
                date = anyDate,
                steps = 0,
                distanceMeters = 0.0,
                activeMinutes = 0,
                kcal = 0.0,
            )
        )
        assertEquals("steps=0 distance=0.0km active=0min kcal=0", note)
    }

    @Test
    fun `distance is rendered with one decimal in km using us locale`() {
        val note = NoteFormatter.format(
            DailyMetrics(
                date = anyDate,
                steps = 1,
                distanceMeters = 1234.0,
                activeMinutes = 0,
                kcal = 0.0,
            )
        )
        assertEquals("steps=1 distance=1.2km active=0min kcal=0", note)
    }

    @Test
    fun `bike ride note carries hashtag duration and no distance`() {
        val text = NoteFormatter.formatBikeRide("workout", 45)
        assertEquals("#workout Bike ride (duration=45 min)", text)
    }

    @Test
    fun `kcal is rounded to whole number`() {
        val note = NoteFormatter.format(
            DailyMetrics(
                date = anyDate,
                steps = 0,
                distanceMeters = 0.0,
                activeMinutes = 0,
                kcal = 1499.6,
            )
        )
        assertEquals("steps=0 distance=0.0km active=0min kcal=1500", note)
    }
}
