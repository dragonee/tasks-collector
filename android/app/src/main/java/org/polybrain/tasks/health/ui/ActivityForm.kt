package org.polybrain.tasks.health.ui

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import org.polybrain.tasks.health.data.HabitMetric

/**
 * What was typed for one metric in the activity dialog, as text: a number;
 * minutes and seconds; upper and lower; an amount and a currency.
 */
data class MetricInput(val first: String = "", val second: String = "")

private val CURRENCY = Regex("[A-Z]{3}")

/**
 * The values to send for what was typed in the activity dialog, by key; a
 * metric left empty is left out. Null when one is filled in wrong, which keeps
 * the dialog from sending.
 */
fun metricValues(metrics: List<HabitMetric>, inputs: Map<String, MetricInput>): JsonObject? {
    val values = mutableMapOf<String, JsonElement>()
    for (metric in metrics) {
        val input = inputs[metric.key] ?: continue
        val first = input.first.trim()
        val second = input.second.trim()
        if (first.isEmpty() && second.isEmpty()) continue
        values[metric.key] = when (metric.kind) {
            "duration" -> {
                val minutes = first.ifEmpty { "0" }.toIntOrNull() ?: return null
                val seconds = second.ifEmpty { "0" }.toIntOrNull() ?: return null
                if (minutes < 0 || seconds !in 0..59) return null
                if (minutes == 0 && seconds == 0) continue
                JsonPrimitive(minutes * 60 + seconds)
            }
            "pressure" -> {
                val upper = first.toIntOrNull() ?: return null
                val lower = second.toIntOrNull() ?: return null
                if (lower <= 0 || upper <= lower) return null
                JsonArray(listOf(JsonPrimitive(upper), JsonPrimitive(lower)))
            }
            "money" -> {
                val amount = number(first) ?: return null
                val currency = second.ifEmpty { "PLN" }.uppercase()
                if (!CURRENCY.matches(currency)) return null
                buildJsonObject {
                    put("amount", amount)
                    put("currency", currency)
                }
            }
            else -> JsonPrimitive(number(first) ?: return null)
        }
    }
    return JsonObject(values)
}

/** The note of an activity: its hashtag (none for a habit without a
 *  keyword), then what was written. */
fun activityNote(keyword: String, note: String): String {
    val hashtag = if (keyword.isBlank()) "" else "#$keyword"
    return listOf(hashtag, note.trim()).filter { it.isNotEmpty() }.joinToString(" ")
}

/** A number as typed, with a dot or a comma. */
private fun number(text: String): Double? =
    text.replace(',', '.').toDoubleOrNull()?.takeIf { it.isFinite() }
