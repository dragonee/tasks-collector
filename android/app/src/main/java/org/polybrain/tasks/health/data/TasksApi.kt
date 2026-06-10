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
    // "Save to trip": link the completion journal entry to this active
    // trip (Story). null = plain save, no trip link.
    @SerialName("story_id") val storyId: Long? = null,
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
data class BoardItem(
    @SerialName("text") val text: String,
    // MoSCoW bucket id: "must" | "should" | "could" | "wont", or null when
    // the item is unclassified.
    @SerialName("moscow") val moscow: String? = null,
    // Nesting level in the board tree (0 = root), used to indent the row.
    @SerialName("depth") val depth: Int = 0,
    @SerialName("done") val done: Boolean = false,
)

@Serializable
data class BoardItemsResponse(
    @SerialName("items") val items: List<BoardItem> = emptyList(),
)

@Serializable
data class PlanItem(
    @SerialName("id") val id: Long,
    @SerialName("pub_date") val pubDate: String,
    // Newline-joined task lines. May be null/blank when the plan exists
    // but has no focus set yet.
    @SerialName("focus") val focus: String? = null,
)

// DRF PageNumberPagination envelope for GET /plans/. We only ever read
// the first page for a single (thread, pub_date) pair, so `results` holds
// at most one plan, but the envelope shape is fixed by the framework.
@Serializable
data class PlanListResponse(
    @SerialName("results") val results: List<PlanItem> = emptyList(),
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
    // Client-generated UUID for exactly-once delivery. The outbox retries on
    // failure, so a request whose response was lost must not create a second
    // note — the server dedupes on this key.
    @SerialName("idempotency_key") val idempotencyKey: String,
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
    @SerialName("type") val type: String, // "journal" | "photo" | "habit" | "other"
    @SerialName("published") val published: String,
    @SerialName("comment") val comment: String? = null,
    @SerialName("habit_slug") val habitSlug: String? = null,
    @SerialName("habit_name") val habitName: String? = null,
    @SerialName("occured") val occured: Boolean? = null,
    @SerialName("note") val note: String? = null,
    // Photo events: short-lived presigned thumbnail URL (null until the
    // server-side thumbnail task finishes), and whether it is ready.
    @SerialName("thumbnail_url") val thumbnailUrl: String? = null,
    @SerialName("ready") val ready: Boolean? = null,
)

@Serializable
data class PhotoPresignRequest(
    @SerialName("story_id") val storyId: Long,
    @SerialName("content_type") val contentType: String,
)

@Serializable
data class PhotoPresignResponse(
    @SerialName("key") val key: String,
    @SerialName("upload_url") val uploadUrl: String,
    @SerialName("expires_at") val expiresAt: String? = null,
)

@Serializable
data class PhotoConfirmRequest(
    @SerialName("story_id") val storyId: Long,
    @SerialName("key") val key: String,
    @SerialName("comment") val comment: String,
    @SerialName("content_type") val contentType: String,
    // Full ISO 8601 timestamp (OffsetDateTime.now().toString()).
    @SerialName("published") val published: String,
    // Client-generated UUID for exactly-once delivery (see TripNoteRequest).
    @SerialName("idempotency_key") val idempotencyKey: String,
)

@Serializable
data class PhotoConfirmResponse(
    @SerialName("ok") val ok: Boolean = false,
    @SerialName("photo_id") val photoId: Long = 0,
)

// Standalone (storyless) photo upload: same two-phase flow as a trip photo,
// but with no `story_id`. The confirm creates a PhotoTaken attached to no trip.
@Serializable
data class StandalonePhotoPresignRequest(
    @SerialName("content_type") val contentType: String,
)

@Serializable
data class StandalonePhotoConfirmRequest(
    @SerialName("key") val key: String,
    @SerialName("comment") val comment: String,
    @SerialName("content_type") val contentType: String,
    @SerialName("published") val published: String,
    @SerialName("idempotency_key") val idempotencyKey: String,
)

@Serializable
data class PhotoOriginalResponse(
    @SerialName("url") val url: String,
)

// Public share link for a trip. The server builds the full absolute URL —
// the client never assembles URLs itself.
@Serializable
data class TripShare(
    @SerialName("uuid") val uuid: String,
    @SerialName("url") val url: String,
)

@Serializable
data class TripShareResponse(
    @SerialName("shared") val shared: Boolean = false,
    @SerialName("share") val share: TripShare? = null,
)

@Serializable
data class TripDetailResponse(
    @SerialName("story") val story: TripSummary,
    @SerialName("events") val events: List<TripEvent> = emptyList(),
    // Null when the trip is not shared (and on older servers).
    @SerialName("share") val share: TripShare? = null,
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

    // Flattened current board (pre-order, depth-annotated) for the
    // "add from board" picker. Date-independent.
    @GET("api/v1/android/board/items/")
    suspend fun listBoardItems(): BoardItemsResponse

    @POST("api/v1/android/task/add/")
    suspend fun addTodayTask(@Body body: TaskTextRequest): OkResponse

    @POST("api/v1/android/task/complete/")
    suspend fun completeTodayTask(@Body body: TaskCompleteRequest): OkResponse

    @POST("api/v1/android/task/delete/")
    suspend fun deleteTodayTask(@Body body: TaskTextRequest): OkResponse

    // Generic DRF Plan endpoint shared with the web frontend. Filtered by
    // thread name (e.g. "Weekly") and the plan's canonical pub_date (for
    // Weekly that's the Sunday ending the week). Token-authenticated like
    // the rest of the client.
    @GET("plans/")
    suspend fun listPlans(
        @Query("thread") thread: String,
        @Query("pub_date") pubDate: String,
    ): PlanListResponse

    @POST("api/v1/android/trip/start/")
    suspend fun startTrip(@Body body: TripStartRequest): TripResponse

    @POST("api/v1/android/trip/stop/")
    suspend fun stopTrip(@Body body: TripStoryIdRequest): TripResponse

    @POST("api/v1/android/trip/update/")
    suspend fun updateTrip(@Body body: TripUpdateRequest): TripResponse

    @POST("api/v1/android/trip/share/")
    suspend fun shareTrip(@Body body: TripStoryIdRequest): TripShareResponse

    @POST("api/v1/android/trip/share/revoke/")
    suspend fun revokeTripShare(@Body body: TripStoryIdRequest): TripShareResponse

    @POST("api/v1/android/trip/note/")
    suspend fun addTripNote(@Body body: TripNoteRequest): TripNoteResponse

    @GET("api/v1/android/trip/list/")
    suspend fun listTrips(
        @Query("page") page: Int = 1,
        @Query("page_size") pageSize: Int = 20,
    ): TripListResponse

    @GET("api/v1/android/trip/{id}/")
    suspend fun tripDetail(@Path("id") storyId: Long): TripDetailResponse

    @POST("api/v1/android/trip/photo/presign/")
    suspend fun presignPhoto(@Body body: PhotoPresignRequest): PhotoPresignResponse

    @POST("api/v1/android/trip/photo/")
    suspend fun addTripPhoto(@Body body: PhotoConfirmRequest): PhotoConfirmResponse

    @GET("api/v1/android/trip/photo/{id}/original/")
    suspend fun photoOriginal(@Path("id") eventId: Long): PhotoOriginalResponse

    @POST("api/v1/android/photo/presign/")
    suspend fun presignStandalonePhoto(
        @Body body: StandalonePhotoPresignRequest,
    ): PhotoPresignResponse

    @POST("api/v1/android/photo/")
    suspend fun addStandalonePhoto(
        @Body body: StandalonePhotoConfirmRequest,
    ): PhotoConfirmResponse
}
