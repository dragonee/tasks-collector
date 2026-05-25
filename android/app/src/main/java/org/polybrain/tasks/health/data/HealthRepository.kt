package org.polybrain.tasks.health.data

import android.content.Context
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.aggregate.AggregationResult
import androidx.health.connect.client.permission.HealthPermission
import androidx.health.connect.client.records.ActiveCaloriesBurnedRecord
import androidx.health.connect.client.records.DistanceRecord
import androidx.health.connect.client.records.ExerciseSessionRecord
import androidx.health.connect.client.records.StepsRecord
import androidx.health.connect.client.records.TotalCaloriesBurnedRecord
import androidx.health.connect.client.request.AggregateGroupByDurationRequest
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
    val kcal: Double,
)

data class BikeSession(
    // Health Connect's stable per-record ID (Metadata.id). Used as a
    // dedup key so the 7-day re-sync window doesn't post the same ride
    // twice.
    val id: String,
    val start: java.time.Instant,
    val durationMinutes: Long,
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
        HealthPermission.getReadPermission(TotalCaloriesBurnedRecord::class),
        HealthPermission.getReadPermission(ActiveCaloriesBurnedRecord::class),
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
                    TotalCaloriesBurnedRecord.ENERGY_TOTAL,
                    ActiveCaloriesBurnedRecord.ACTIVE_CALORIES_TOTAL,
                ),
                timeRangeFilter = range,
            )
        )

        val steps = aggregate[StepsRecord.COUNT_TOTAL] ?: 0L
        val distanceMeters = aggregate[DistanceRecord.DISTANCE_TOTAL]?.inMeters ?: 0.0

        // Prefer total energy when available; fall back to active. Some HC writers
        // populate only one. Google Fit's main "kcal" number is total.
        val totalKcal = aggregate[TotalCaloriesBurnedRecord.ENERGY_TOTAL]?.inKilocalories
        val activeKcal = aggregate[ActiveCaloriesBurnedRecord.ACTIVE_CALORIES_TOTAL]?.inKilocalories
        val kcal = totalKcal ?: activeKcal ?: 0.0

        val activeMinutes = computeActiveMinutes(client, range)

        return DailyMetrics(
            date = date,
            steps = steps,
            distanceMeters = distanceMeters,
            activeMinutes = activeMinutes,
            kcal = kcal,
        )
    }

    /**
     * Reads completed bike rides for the day. Filters [ExerciseSessionRecord]
     * by [ExerciseSessionRecord.EXERCISE_TYPE_BIKING] and returns each
     * session with its Health Connect record ID (for client-side dedup
     * across the rolling re-sync window) and rounded-minute duration.
     */
    suspend fun bikeSessions(date: LocalDate, zone: ZoneId = ZoneId.systemDefault()): List<BikeSession> {
        val client = client()
        val startInstant = date.atStartOfDay(zone).toInstant()
        val endInstant = date.plusDays(1).atStartOfDay(zone).toInstant()
        val range = TimeRangeFilter.between(startInstant, endInstant)

        val sessions = client.readRecords(
            ReadRecordsRequest(
                recordType = ExerciseSessionRecord::class,
                timeRangeFilter = range,
            )
        ).records

        val results = ArrayList<BikeSession>()
        for (session in sessions) {
            if (session.exerciseType != ExerciseSessionRecord.EXERCISE_TYPE_BIKING) continue
            val duration = Duration.between(session.startTime, session.endTime)
            if (duration.isZero || duration.isNegative) continue
            val minutes = (duration.seconds + 30) / 60
            if (minutes <= 0) continue
            results.add(
                BikeSession(
                    id = session.metadata.id,
                    start = session.startTime,
                    durationMinutes = minutes,
                )
            )
        }
        return results
    }

    /**
     * Approximates Google Fit's "minutes of movement". The previous "any minute
     * a non-empty step record touches" rule over-counted because Health Connect
     * step records often span long windows (a watch writing one record per hour
     * with the total) — that marked the whole window as active even if the user
     * sat for most of it.
     *
     * Instead: bucket the day into 1-minute slices via [aggregateGroupByDuration]
     * (which proportionally distributes each source record's step count across
     * its time range) and count minutes whose step count meets a low-intensity-
     * walking threshold. Add explicit exercise sessions on top, deduped by
     * minute bucket so an overlapping logged workout can't double-count.
     */
    private suspend fun computeActiveMinutes(
        client: HealthConnectClient,
        range: TimeRangeFilter,
    ): Long {
        val perMinute = client.aggregateGroupByDuration(
            AggregateGroupByDurationRequest(
                metrics = setOf(StepsRecord.COUNT_TOTAL),
                timeRangeFilter = range,
                timeRangeSlicer = Duration.ofMinutes(1),
            )
        )

        val activeMinuteBuckets = HashSet<Long>()
        for (bucket in perMinute) {
            val steps = bucket.result[StepsRecord.COUNT_TOTAL] ?: 0L
            if (steps >= ACTIVE_STEP_THRESHOLD_PER_MINUTE) {
                activeMinuteBuckets.add(bucket.startTime.epochSecond / 60)
            }
        }

        val sessions = client.readRecords(
            ReadRecordsRequest(
                recordType = ExerciseSessionRecord::class,
                timeRangeFilter = range,
            )
        ).records
        for (session in sessions) {
            val start = session.startTime
            val end = session.endTime
            if (!end.isAfter(start)) continue
            val startMinute = start.epochSecond / 60
            val lastMinute = (end.epochSecond - 1) / 60
            for (m in startMinute..lastMinute) activeMinuteBuckets.add(m)
        }

        return activeMinuteBuckets.size.toLong()
    }

    private companion object {
        /**
         * Steps per minute that qualify a minute as "active". 30 is below the
         * ~80–100 spm of brisk walking but above ambient noise from desk
         * fidgeting; it roughly corresponds to a slow stroll. Tune downward to
         * be more permissive, upward to match a brisker-walk definition.
         */
        const val ACTIVE_STEP_THRESHOLD_PER_MINUTE = 30L
    }
}
