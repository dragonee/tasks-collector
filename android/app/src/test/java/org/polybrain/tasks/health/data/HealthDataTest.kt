package org.polybrain.tasks.health.data

import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class HealthDataTest {

    // As TasksClient configures it.
    private val json = Json {
        ignoreUnknownKeys = true
        encodeDefaults = true
    }

    @Test
    fun `health data says what each role records`() {
        val data = json.decodeFromString<HealthDataResponse>(
            """
            {"weight_kg": null, "recorded_at": null,
             "roles": {
               "weight": {"name": "Weight", "keyword": "weight", "metrics": [
                 {"key": "weight", "label": "Weight", "kind": "number", "unit": "kg", "decimals": 1}]},
               "bike-ride": {"name": "Workout", "keyword": "", "metrics": []}}}
            """,
        )

        assertNull(data.weightKg)
        assertEquals(
            RoleHabit(
                name = "Weight",
                keyword = "weight",
                metrics = listOf(HabitMetric("weight", "Weight", "number", "kg", 1)),
            ),
            data.roles["weight"],
        )
        assertEquals("", data.roles.getValue("bike-ride").keyword)
    }

    @Test
    fun `a server that says no roles gives none`() {
        val data = json.decodeFromString<HealthDataResponse>(
            """{"weight_kg": 80.5, "recorded_at": "2026-11-19T08:00:00+01:00"}""",
        )

        assertEquals(80.5, data.weightKg!!, 0.0)
        assertTrue(data.roles.isEmpty())
    }
}
