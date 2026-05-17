package org.polybrain.tasks.health.sync

import org.polybrain.tasks.health.data.DailyMetrics
import java.util.Locale

object NoteFormatter {

    fun format(metrics: DailyMetrics): String {
        val km = metrics.distanceMeters / 1000.0
        val distanceStr = String.format(Locale.US, "%.1f", km)
        val kcalStr = String.format(Locale.US, "%.0f", metrics.kcal)
        return "steps=${metrics.steps} " +
            "distance=${distanceStr}km " +
            "active=${metrics.activeMinutes}min " +
            "kcal=$kcalStr"
    }
}
