package org.polybrain.tasks.health.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Query

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

@Serializable
data class OkResponse(
    @SerialName("ok") val ok: Boolean = false,
)

@Serializable
data class TaskTextRequest(
    @SerialName("text") val text: String,
    @SerialName("date") val date: String,
)

@Serializable
data class TaskCompleteRequest(
    @SerialName("text") val text: String,
    @SerialName("done") val done: Boolean,
    @SerialName("date") val date: String,
)

@Serializable
data class TodayTask(
    @SerialName("text") val text: String,
    @SerialName("done") val done: Boolean,
)

@Serializable
data class TodayTasksResponse(
    @SerialName("items") val items: List<TodayTask> = emptyList(),
)

interface TasksApi {
    @POST("api/v1/habit/track/")
    suspend fun trackHabit(@Body body: TrackHabitRequest): TrackHabitResponse

    @GET("api/v1/android/task/today/")
    suspend fun listTodayTasks(@Query("date") date: String): TodayTasksResponse

    @POST("api/v1/android/task/add/")
    suspend fun addTodayTask(@Body body: TaskTextRequest): OkResponse

    @POST("api/v1/android/task/complete/")
    suspend fun completeTodayTask(@Body body: TaskCompleteRequest): OkResponse

    @POST("api/v1/android/task/delete/")
    suspend fun deleteTodayTask(@Body body: TaskTextRequest): OkResponse
}
