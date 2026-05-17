package com.dragonee.tasks.health.sync

import com.dragonee.tasks.health.data.DailyMetrics
import java.util.Locale

object NoteFormatter {

    fun format(metrics: DailyMetrics): String {
        val km = metrics.distanceMeters / 1000.0
        val distanceStr = String.format(Locale.US, "%.1f", km)
        return "steps=${metrics.steps} distance=${distanceStr}km active=${metrics.activeMinutes}min"
    }
}
