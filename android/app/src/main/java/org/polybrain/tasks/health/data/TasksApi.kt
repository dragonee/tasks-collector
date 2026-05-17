package org.polybrain.tasks.health.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import retrofit2.http.Body
import retrofit2.http.POST

@Serializable
data class TrackHabitRequest(
    @SerialName("keyword") val keyword: String,
    @SerialName("date") val date: String,
    @SerialName("note") val note: String,
)

@Serializable
data class TrackHabitResponse(
    @SerialName("ok") val ok: Boolean,
)

interface TasksApi {
    @POST("api/v1/habit/track/")
    suspend fun trackHabit(@Body body: TrackHabitRequest): TrackHabitResponse
}
