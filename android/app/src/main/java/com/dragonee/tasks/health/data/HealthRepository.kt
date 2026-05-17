package com.dragonee.tasks.health.data

import android.content.Context
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.aggregate.AggregationResult
import androidx.health.connect.client.permission.HealthPermission
import androidx.health.connect.client.records.DistanceRecord
import androidx.health.connect.client.records.ExerciseSessionRecord
import androidx.health.connect.client.records.StepsRecord
import androidx.health.connect.client.request.AggregateRequest
import androidx.health.connect.client.request.ReadRecordsRequest
import androidx.health.connect.client.time.TimeRangeFilter
import java.time.Duration
import java.time.LocalDate
import java.time.ZoneId

data class DailyMetrics(
    val date: LocalDate,
    val steps: Long,
    val distanceMeters: Double,
    val activeMinutes: Long,
)

/**
 * The string constant for Health Connect's background-read permission. Spelled
 * out here (rather than imported from [HealthPermission]) because the SDK
 * constant name has shifted across alpha versions; the manifest permission
 * identifier is the stable contract.
 */
private const val PERMISSION_READ_HEALTH_DATA_IN_BACKGROUND =
    "android.permission.health.READ_HEALTH_DATA_IN_BACKGROUND"

class HealthRepository(private val context: Context) {

    val permissions: Set<String> = setOf(
        HealthPermission.getReadPermission(StepsRecord::class),
        HealthPermission.getReadPermission(DistanceRecord::class),
        HealthPermission.getReadPermission(ExerciseSessionRecord::class),
        PERMISSION_READ_HEALTH_DATA_IN_BACKGROUND,
    )

    fun availability(): Int = HealthConnectClient.getSdkStatus(context)

    fun client(): HealthConnectClient = HealthConnectClient.getOrCreate(context)

    suspend fun hasAllPermissions(): Boolean {
        val granted = client().permissionController.getGrantedPermissions()
        return granted.containsAll(permissions)
    }

    suspend fun aggregateDay(date: LocalDate, zone: ZoneId = ZoneId.systemDefault()): DailyMetrics {
        val client = client()
        val startInstant = date.atStartOfDay(zone).toInstant()
        val endInstant = date.plusDays(1).atStartOfDay(zone).toInstant()
        val range = TimeRangeFilter.between(startInstant, endInstant)

        val aggregate: AggregationResult = client.aggregate(
            AggregateRequest(
                metrics = setOf(
                    StepsRecord.COUNT_TOTAL,
                    DistanceRecord.DISTANCE_TOTAL,
                ),
                timeRangeFilter = range,
            )
        )

        val steps = aggregate[StepsRecord.COUNT_TOTAL] ?: 0L
        val distanceMeters = aggregate[DistanceRecord.DISTANCE_TOTAL]?.inMeters ?: 0.0

        val sessions = client.readRecords(
            ReadRecordsRequest(
                recordType = ExerciseSessionRecord::class,
                timeRangeFilter = range,
            )
        ).records

        val activeMinutes = sessions.sumOf { session ->
            Duration.between(session.startTime, session.endTime).toMinutes()
        }

        return DailyMetrics(
            date = date,
            steps = steps,
            distanceMeters = distanceMeters,
            activeMinutes = activeMinutes,
        )
    }
}
