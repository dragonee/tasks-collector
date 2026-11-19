package org.polybrain.tasks.health.ui

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import org.polybrain.tasks.health.data.HabitMetric

class ActivityFormTest {

    private val weight = HabitMetric(key = "weight", kind = "number", unit = "kg", decimals = 1)
    private val duration = HabitMetric(key = "duration", kind = "duration")
    private val pressure = HabitMetric(key = "pressure", kind = "pressure")
    private val amount = HabitMetric(key = "amount", kind = "money")

    private fun json(metrics: List<HabitMetric>, inputs: Map<String, MetricInput>): String? =
        metricValues(metrics, inputs)?.toString()

    @Test
    fun `each kind is sent as the server takes it`() {
        assertEquals(
            """{"weight":80.5,"duration":1525,"pressure":[120,80],"amount":{"amount":90.0,"currency":"EUR"}}""",
            json(
                listOf(weight, duration, pressure, amount),
                mapOf(
                    "weight" to MetricInput("80,5"),
                    "duration" to MetricInput("25", "25"),
                    "pressure" to MetricInput("120", "80"),
                    "amount" to MetricInput("90", "eur"),
                ),
            ),
        )
    }

    @Test
    fun `a metric left empty is left out`() {
        assertEquals(
            """{"weight":80.0}""",
            json(
                listOf(weight, duration, amount),
                mapOf("weight" to MetricInput("80"), "duration" to MetricInput("0", "0")),
            ),
        )
    }

    @Test
    fun `money without a currency is in zloty`() {
        assertEquals(
            """{"amount":{"amount":45.0,"currency":"PLN"}}""",
            json(listOf(amount), mapOf("amount" to MetricInput("45"))),
        )
    }

    @Test
    fun `something filled in wrong keeps the dialog from sending`() {
        assertNull(json(listOf(weight), mapOf("weight" to MetricInput("heavy"))))
        assertNull(json(listOf(pressure), mapOf("pressure" to MetricInput("80", "120"))))
        assertNull(json(listOf(pressure), mapOf("pressure" to MetricInput("120"))))
        assertNull(json(listOf(amount), mapOf("amount" to MetricInput("90", "euro"))))
    }

    @Test
    fun `the note is the hashtag and what was written`() {
        assertEquals("#running", activityNote("running", "  "))
        assertEquals("#running park", activityNote("running", " park "))
    }

    @Test
    fun `a habit without a keyword has no hashtag`() {
        assertEquals("", activityNote("", "  "))
        assertEquals("park", activityNote("", " park "))
    }
}
