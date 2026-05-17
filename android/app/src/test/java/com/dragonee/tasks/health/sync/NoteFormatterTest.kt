package com.dragonee.tasks.health.sync

import com.dragonee.tasks.health.data.DailyMetrics
import java.time.LocalDate
import org.junit.Assert.assertEquals
import org.junit.Test

class NoteFormatterTest {

    private val anyDate: LocalDate = LocalDate.of(2026, 5, 17)

    @Test
    fun `formats steps distance and active minutes`() {
        val note = NoteFormatter.format(
            DailyMetrics(
                date = anyDate,
                steps = 8520,
                distanceMeters = 6234.5,
                activeMinutes = 42,
            )
        )
        assertEquals("steps=8520 distance=6.2km active=42min", note)
    }

    @Test
    fun `zero metrics still render with zero values`() {
        val note = NoteFormatter.format(
            DailyMetrics(
                date = anyDate,
                steps = 0,
                distanceMeters = 0.0,
                activeMinutes = 0,
            )
        )
        assertEquals("steps=0 distance=0.0km active=0min", note)
    }

    @Test
    fun `distance is rendered with one decimal in km using us locale`() {
        val note = NoteFormatter.format(
            DailyMetrics(
                date = anyDate,
                steps = 1,
                distanceMeters = 1234.0,
                activeMinutes = 0,
            )
        )
        assertEquals("steps=1 distance=1.2km active=0min", note)
    }
}
