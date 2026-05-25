package org.polybrain.tasks.health.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Path
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
data class TrackHabitTextRequest(
    // Single line starting with '#' or '!'. The server parses out the
    // hashtag and creates one HabitTracked per tag found, so multiple
    // entries per day for the same habit are supported (unlike the
    // idempotent /api/v1/habit/track/).
    @SerialName("text") val text: String,
    // ISO 8601 timestamp; the server uses this as the event's published
    // time so the entry lands on the day the activity actually happened.
    @SerialName("published") val published: String,
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
    // Full ISO 8601 timestamp (OffsetDateTime.now().toString()) — the
    // device's wall-clock moment of the tap. The server uses it both to
    // derive the day for Plan/Reflection writes and as the published
    // time of any JournalAdded recorded for this completion.
    @SerialName("date") val date: String,
    // Free-form journal note typed in the modal. null = no journal entry
    // (uncheck path or pre-modal builds); empty string = create entry
    // with just the [x] marker line.
    @SerialName("note") val note: String? = null,
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

@Serializable
data class TripSummary(
    @SerialName("id") val id: Long,
    @SerialName("type") val type: String,
    @SerialName("title") val title: String,
    @SerialName("started") val started: String,
    @SerialName("stopped") val stopped: String? = null,
)

@Serializable
data class TripStartRequest(
    @SerialName("title") val title: String? = null,
    @SerialName("type") val type: String = "trip",
)

@Serializable
data class TripStoryIdRequest(
    @SerialName("story_id") val storyId: Long,
)

@Serializable
data class TripUpdateRequest(
    @SerialName("story_id") val storyId: Long,
    @SerialName("title") val title: String,
)

@Serializable
data class TripNoteRequest(
    @SerialName("story_id") val storyId: Long,
    @SerialName("comment") val comment: String,
    // Full ISO 8601 timestamp (OffsetDateTime.now().toString()).
    @SerialName("published") val published: String,
)

@Serializable
data class TripResponse(
    @SerialName("story") val story: TripSummary,
)

@Serializable
data class TripNoteResponse(
    @SerialName("ok") val ok: Boolean = false,
    @SerialName("journal_id") val journalId: Long = 0,
)

@Serializable
data class TripListResponse(
    @SerialName("active") val active: List<TripSummary> = emptyList(),
    @SerialName("history") val history: List<TripSummary> = emptyList(),
    @SerialName("total_history") val totalHistory: Int = 0,
    @SerialName("page") val page: Int = 1,
    @SerialName("page_size") val pageSize: Int = 20,
)

@Serializable
data class TripEvent(
    @SerialName("id") val id: Long,
    @SerialName("type") val type: String, // "journal" | "habit" | "other"
    @SerialName("published") val published: String,
    @SerialName("comment") val comment: String? = null,
    @SerialName("habit_slug") val habitSlug: String? = null,
    @SerialName("habit_name") val habitName: String? = null,
    @SerialName("occured") val occured: Boolean? = null,
    @SerialName("note") val note: String? = null,
)

@Serializable
data class TripDetailResponse(
    @SerialName("story") val story: TripSummary,
    @SerialName("events") val events: List<TripEvent> = emptyList(),
)

interface TasksApi {
    @POST("api/v1/habit/track/")
    suspend fun trackHabit(@Body body: TrackHabitRequest): TrackHabitResponse

    // Non-API web endpoint (no /api/v1/ prefix) that accepts a free-form
    // habit line and creates one HabitTracked per parsed hashtag. Used for
    // per-event activities like individual bike rides, where the
    // upsert-by-(habit, date) behavior of /api/v1/habit/track/ would
    // collapse multiple events into one.
    @POST("habit/track/")
    suspend fun trackHabitText(@Body body: TrackHabitTextRequest): OkResponse

    @GET("api/v1/android/task/today/")
    suspend fun listTodayTasks(@Query("date") date: String): TodayTasksResponse

    @POST("api/v1/android/task/add/")
    suspend fun addTodayTask(@Body body: TaskTextRequest): OkResponse

    @POST("api/v1/android/task/complete/")
    suspend fun completeTodayTask(@Body body: TaskCompleteRequest): OkResponse

    @POST("api/v1/android/task/delete/")
    suspend fun deleteTodayTask(@Body body: TaskTextRequest): OkResponse

    @POST("api/v1/android/trip/start/")
    suspend fun startTrip(@Body body: TripStartRequest): TripResponse

    @POST("api/v1/android/trip/stop/")
    suspend fun stopTrip(@Body body: TripStoryIdRequest): TripResponse

    @POST("api/v1/android/trip/update/")
    suspend fun updateTrip(@Body body: TripUpdateRequest): TripResponse

    @POST("api/v1/android/trip/note/")
    suspend fun addTripNote(@Body body: TripNoteRequest): TripNoteResponse

    @GET("api/v1/android/trip/list/")
    suspend fun listTrips(
        @Query("page") page: Int = 1,
        @Query("page_size") pageSize: Int = 20,
    ): TripListResponse

    @GET("api/v1/android/trip/{id}/")
    suspend fun tripDetail(@Path("id") storyId: Long): TripDetailResponse
}
