package org.polybrain.tasks.health.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import retrofit2.Response
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

// One option in the "track a habit" picker. Mirrors the `habit/keywords/mine/`
// payload — a HabitKeyword row with its parent Habit nested. The lenient JSON
// config ignores the extra habit fields the server also sends (slug,
// description, today_tracked).
@Serializable
data class HabitKeyword(
    @SerialName("id") val id: Long,
    @SerialName("keyword") val keyword: String,
    @SerialName("habit") val habit: HabitRef? = null,
)

@Serializable
data class HabitRef(
    @SerialName("id") val id: Long = 0,
    @SerialName("name") val name: String = "",
)

// Server-derived health data for the Health screen. Currently just the most
// recently recorded body weight and when it was recorded; both null when
// nothing has been recorded yet.
@Serializable
data class HealthDataResponse(
    @SerialName("weight_kg") val weightKg: Double? = null,
    @SerialName("recorded_at") val recordedAt: String? = null,
)

// A task as the server describes it (api/v1/tasks/). One of today's lines, or
// of the week's plan.
@Serializable
data class Task(
    // Null for a plain line of a plan: one nothing was done with as a task
    // yet. Planning its text (planText) makes it a task and gives it an id.
    @SerialName("id") val id: String? = null,
    // As written, e.g. "Do x (3)", and as lists show it: a counted task with
    // the step it is on, "Do x (2/3)".
    @SerialName("text") val text: String,
    @SerialName("display") val display: String = "",
    @SerialName("done") val done: Boolean = false,
    // "~" (better) / "^" (best) for a task done with that mark.
    @SerialName("mark") val mark: String? = null,
    // Steps: one for a plain task; a counted one is done at doneCount >= total
    // and may go past it ("add another").
    @SerialName("total") val total: Int = 1,
    @SerialName("done_count") val doneCount: Int = 0,
) {
    /** What a row shows. */
    val shown: String get() = display.ifEmpty { text }

    /** What tells this row from the others: its task, or its text while it
     * is a plain line. */
    val key: String get() = id ?: "text:$text"

    /** A counted task that is done: tapping it offers another step or taking
     * the last one back, instead of unticking straight away. */
    val isCountedAndDone: Boolean get() = total > 1 && doneCount >= total
}

/**
 * What is left of the week's plan to offer on a day: the tasks that are not
 * done (wherever they were ticked) and not on that day's list already.
 */
fun weekPlanLeft(weekPlan: List<Task>, today: List<Task>): List<Task> {
    val onTheDay = today.map { it.key }.toSet()
    return weekPlan.filterNot { it.done || it.key in onTheDay }
}

@Serializable
data class AgendaPlan(
    @SerialName("thread") val thread: String = "",
    @SerialName("pub_date") val pubDate: String = "",
    @SerialName("tasks") val tasks: List<Task> = emptyList(),
)

// GET api/v1/tasks/agenda/?date= — the plan of that day, of its week and of
// its month. Done is the task's: a task of the week ticked on another day
// comes back done here.
@Serializable
data class AgendaResponse(
    @SerialName("daily") val daily: AgendaPlan = AgendaPlan(),
    @SerialName("weekly") val weekly: AgendaPlan = AgendaPlan(),
    @SerialName("monthly") val monthly: AgendaPlan = AgendaPlan(),
)

// POST api/v1/tasks/ — plan something typed on the plan of [thread] that the
// day [date] falls in. The server answers with the task of that text if the
// user has one planned already (a line of the week pulled into a day), else a
// new one. Two request types rather than one with nulls: the client encodes
// defaults, and the server wants either text or an item, not both.
@Serializable
data class PlanTextRequest(
    @SerialName("text") val text: String,
    @SerialName("date") val date: String,
    @SerialName("thread") val thread: String = "Daily",
)

// POST api/v1/tasks/ — plan a board item (an unscheduled task becomes a task).
@Serializable
data class PlanItemRequest(
    @SerialName("board_id") val boardId: Long,
    @SerialName("item_id") val itemId: String,
    @SerialName("date") val date: String,
    @SerialName("thread") val thread: String = "Daily",
)

// One of the user's plans: the one of [thread] that the day [date] falls in.
@Serializable
data class PlanRef(
    @SerialName("date") val date: String,
    @SerialName("thread") val thread: String = "Daily",
)

@Serializable
data class TaskMoveRequest(
    @SerialName("from_date") val fromDate: String,
    @SerialName("to_date") val toDate: String,
    @SerialName("thread") val thread: String = "Daily",
)

@Serializable
data class TaskCompleteRequest(
    // The day it was done on for the user (YYYY-MM-DD): the reflection it
    // lands in.
    @SerialName("day") val day: String,
    // Full ISO 8601 timestamp — the moment of the tap, which is also the
    // published time of the journal entry a note makes.
    @SerialName("at") val at: String,
    // Free-form journal note typed in the modal. null or empty = no journal
    // entry, unless it is saved to a trip.
    @SerialName("note") val note: String? = null,
    // "Save to trip": link the completion journal entry to this active
    // trip (Story). null = plain save, no trip link.
    @SerialName("story_id") val storyId: Long? = null,
    // Sent again unchanged on a retry: the server completes once per key.
    @SerialName("idempotency_key") val idempotencyKey: String,
)

@Serializable
data class BoardItem(
    // The item's id and its board: what PlanItemRequest names it by.
    @SerialName("id") val id: String? = null,
    @SerialName("board_id") val boardId: Long = 0,
    // Whether it has a task already; otherwise it is an unscheduled task.
    @SerialName("planned") val planned: Boolean = false,
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

// Append a free-typed unscheduled task to the caller's current board.
// `thread-name` is intentionally omitted: the server defaults it to the user's
// board thread (the same board /board/items/ returns), so the client never
// names the board.
@Serializable
data class UnscheduledTaskRequest(
    @SerialName("text") val text: String,
)

// boards/append/ echoes the full updated board (BoardSerializer). The client
// only needs to know the call succeeded, so this field-less type discards the
// body (the lenient Json drops all unknown keys).
@Serializable
class UnscheduledTaskResponse

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
data class TripStopRequest(
    @SerialName("story_id") val storyId: Long,
    // Full ISO 8601 timestamp for when the trip actually ended — the
    // "I got home yesterday and forgot to stop it" case. null stops it now.
    // The server clamps a future value to its own now and rejects anything
    // before the trip started.
    @SerialName("stopped") val stopped: String? = null,
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
    // Hex SHA-256 of the bytes; lets the server dedup the same image within a
    // trip even across distinct idempotency keys (re-picks). Null if unknown.
    @SerialName("content_hash") val contentHash: String? = null,
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

    // The current user's available habit keywords for the "track a habit"
    // picker. Scoped to the profile's selection (the server falls back to all
    // keywords when none are chosen) and, because it filters by `date`,
    // excludes habits already tracked that day. Returns a bare JSON array.
    @GET("habit/keywords/mine/")
    suspend fun listHabitKeywords(@Query("date") date: String): List<HabitKeyword>

    // Server-derived health data (currently the last recorded body weight).
    @GET("api/v1/android/health/data/")
    suspend fun healthData(): HealthDataResponse

    @GET("api/v1/tasks/agenda/")
    suspend fun agenda(@Query("date") date: String): AgendaResponse

    // Flattened current board (pre-order, depth-annotated) for the
    // "add from board" picker. Date-independent.
    @GET("api/v1/android/board/items/")
    suspend fun listBoardItems(): BoardItemsResponse

    // Non-API web endpoint (no /api/v1/ prefix; token auth via DRF defaults,
    // like plans/ and habit/track/). Appends an unscheduled task to the
    // caller's current board — for capturing something to do later, not
    // scheduling it on a day. The server resolves which board from the profile
    // default.
    @POST("boards/append/")
    suspend fun appendUnscheduledTask(
        @Body body: UnscheduledTaskRequest,
    ): UnscheduledTaskResponse

    @POST("api/v1/tasks/")
    suspend fun planText(@Body body: PlanTextRequest): Task

    @POST("api/v1/tasks/")
    suspend fun planItem(@Body body: PlanItemRequest): Task

    // Put a task on another of the user's plans as well.
    @POST("api/v1/tasks/{id}/plan/")
    suspend fun planTask(@Path("id") id: String, @Body body: PlanRef): Task

    // Take a task off a plan. 204 when nothing remembers it and it is gone,
    // else the task; either way there is nothing to read.
    @POST("api/v1/tasks/{id}/unplan/")
    suspend fun unplanTask(@Path("id") id: String, @Body body: PlanRef): Response<Unit>

    @POST("api/v1/tasks/{id}/move/")
    suspend fun moveTask(@Path("id") id: String, @Body body: TaskMoveRequest): Task

    @POST("api/v1/tasks/{id}/complete/")
    suspend fun completeTask(
        @Path("id") id: String,
        @Body body: TaskCompleteRequest,
    ): Task

    // Take back the last step done.
    @POST("api/v1/tasks/{id}/reopen/")
    suspend fun reopenTask(@Path("id") id: String): Task

    @POST("api/v1/android/trip/start/")
    suspend fun startTrip(@Body body: TripStartRequest): TripResponse

    @POST("api/v1/android/trip/stop/")
    suspend fun stopTrip(@Body body: TripStopRequest): TripResponse

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
