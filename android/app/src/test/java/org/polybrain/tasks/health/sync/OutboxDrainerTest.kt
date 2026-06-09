package org.polybrain.tasks.health.sync

import java.io.File
import java.io.IOException
import java.nio.file.Files
import kotlinx.coroutines.test.runTest
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.polybrain.tasks.health.data.BoardItemsResponse
import org.polybrain.tasks.health.data.Outbox
import org.polybrain.tasks.health.data.OkResponse
import org.polybrain.tasks.health.data.PhotoConfirmRequest
import org.polybrain.tasks.health.data.PhotoConfirmResponse
import org.polybrain.tasks.health.data.PhotoOriginalResponse
import org.polybrain.tasks.health.data.PhotoPresignRequest
import org.polybrain.tasks.health.data.PhotoPresignResponse
import org.polybrain.tasks.health.data.PlanListResponse
import org.polybrain.tasks.health.data.StandalonePhotoConfirmRequest
import org.polybrain.tasks.health.data.StandalonePhotoPresignRequest
import org.polybrain.tasks.health.data.TaskCompleteRequest
import org.polybrain.tasks.health.data.TaskTextRequest
import org.polybrain.tasks.health.data.TasksApi
import org.polybrain.tasks.health.data.TodayTasksResponse
import org.polybrain.tasks.health.data.TrackHabitRequest
import org.polybrain.tasks.health.data.TrackHabitResponse
import org.polybrain.tasks.health.data.TrackHabitTextRequest
import org.polybrain.tasks.health.data.TripDetailResponse
import org.polybrain.tasks.health.data.TripListResponse
import org.polybrain.tasks.health.data.TripNoteRequest
import org.polybrain.tasks.health.data.TripNoteResponse
import org.polybrain.tasks.health.data.TripResponse
import org.polybrain.tasks.health.data.TripStartRequest
import org.polybrain.tasks.health.data.TripStoryIdRequest
import org.polybrain.tasks.health.data.TripUpdateRequest
import retrofit2.HttpException
import retrofit2.Response

class OutboxDrainerTest {

    private lateinit var dir: File
    private lateinit var outbox: Outbox

    @Before
    fun setUp() {
        dir = Files.createTempDirectory("drainer-test").toFile()
        outbox = Outbox(dir)
    }

    @After
    fun tearDown() {
        dir.deleteRecursively()
    }

    private fun httpException(code: Int) =
        HttpException(Response.error<Any>(code, "err".toResponseBody(null)))

    private val noopPut = OutboxDrainer.PhotoPutter { _, _, _ -> }

    @Test
    fun `note success sends idempotency key and reports Sent`() = runTest {
        val item = outbox.enqueueNote(5L, "hello", "2026-06-06T10:00:00Z")
        val api = FakeApi()
        val outcome = OutboxDrainer.process(item, api, outbox, noopPut)
        assertTrue(outcome is OutboxDrainer.Outcome.Sent)
        assertEquals(1, api.noteRequests.size)
        assertEquals(item.id, api.noteRequests.single().idempotencyKey)
        assertEquals(5L, api.noteRequests.single().storyId)
    }

    @Test
    fun `photo first send presigns puts confirms and marks uploaded`() = runTest {
        val item = outbox.enqueuePhoto(2L, "cap", "t", "image/jpeg", byteArrayOf(1, 2, 3))
        val api = FakeApi(presignKey = "trips/2/k.jpg", presignUrl = "https://put/x")
        var putCalls = 0
        val put = OutboxDrainer.PhotoPutter { url, _, _ ->
            putCalls++
            assertEquals("https://put/x", url)
        }
        val outcome = OutboxDrainer.process(item, api, outbox, put)
        assertTrue(outcome is OutboxDrainer.Outcome.Sent)
        assertEquals(1, putCalls)
        assertEquals(1, api.presignRequests.size)
        val confirm = api.confirmRequests.single()
        assertEquals("trips/2/k.jpg", confirm.key)
        assertEquals(item.id, confirm.idempotencyKey)
        // The resume flag is persisted on the returned item.
        assertTrue((outcome as OutboxDrainer.Outcome.Sent).item.uploaded)
    }

    @Test
    fun `photo retry skips re-upload when already uploaded`() = runTest {
        val base = outbox.enqueuePhoto(2L, "cap", "t", "image/jpeg", byteArrayOf(1, 2, 3))
        // Simulate a previous run that uploaded but failed at confirm.
        val resumed = base.copy(uploaded = true, presignedKey = "trips/2/already.jpg")
        outbox.update(resumed)
        val api = FakeApi()
        var putCalls = 0
        val put = OutboxDrainer.PhotoPutter { _, _, _ -> putCalls++ }
        val outcome = OutboxDrainer.process(resumed, api, outbox, put)
        assertTrue(outcome is OutboxDrainer.Outcome.Sent)
        assertEquals(0, putCalls)
        assertEquals(0, api.presignRequests.size)
        assertEquals("trips/2/already.jpg", api.confirmRequests.single().key)
    }

    @Test
    fun `standalone photo presigns and confirms via storyless endpoints`() = runTest {
        // storyId = null marks a standalone photo (a PhotoTaken with no trip).
        val item = outbox.enqueuePhoto(null, "cap", "t", "image/jpeg", byteArrayOf(9))
        val api = FakeApi(presignKey = "photos/7/k.jpg", presignUrl = "https://put/s")
        var putCalls = 0
        val put = OutboxDrainer.PhotoPutter { url, _, _ ->
            putCalls++
            assertEquals("https://put/s", url)
        }
        val outcome = OutboxDrainer.process(item, api, outbox, put)
        assertTrue(outcome is OutboxDrainer.Outcome.Sent)
        assertEquals(1, putCalls)
        // The trip endpoints are never touched; the storyless ones are.
        assertEquals(0, api.presignRequests.size)
        assertEquals(0, api.confirmRequests.size)
        assertEquals(1, api.standalonePresignRequests.size)
        val confirm = api.standaloneConfirmRequests.single()
        assertEquals("photos/7/k.jpg", confirm.key)
        assertEquals(item.id, confirm.idempotencyKey)
    }

    @Test
    fun `4xx is permanent`() = runTest {
        val item = outbox.enqueueNote(1L, "x", "t")
        val api = FakeApi(noteError = httpException(409))
        val outcome = OutboxDrainer.process(item, api, outbox, noopPut)
        assertTrue(outcome is OutboxDrainer.Outcome.Permanent)
    }

    @Test
    fun `5xx is retryable`() = runTest {
        val item = outbox.enqueueNote(1L, "x", "t")
        val api = FakeApi(noteError = httpException(503))
        val outcome = OutboxDrainer.process(item, api, outbox, noopPut)
        assertTrue(outcome is OutboxDrainer.Outcome.Retry)
    }

    @Test
    fun `network error is retryable`() = runTest {
        val item = outbox.enqueueNote(1L, "x", "t")
        val api = FakeApi(noteError = IOException("no route to host"))
        val outcome = OutboxDrainer.process(item, api, outbox, noopPut)
        assertTrue(outcome is OutboxDrainer.Outcome.Retry)
    }

    @Test
    fun `missing photo bytes is permanent not an endless retry`() = runTest {
        val item = outbox.enqueuePhoto(1L, "c", "t", "image/jpeg", byteArrayOf(7))
        // Delete the bytes file but keep the item (simulates corruption).
        outbox.photoFile(item)!!.delete()
        val api = FakeApi()
        val outcome = OutboxDrainer.process(item, api, outbox, noopPut)
        assertTrue(outcome is OutboxDrainer.Outcome.Permanent)
        assertEquals(0, api.presignRequests.size)
    }

    /**
     * Fake covering the whole [TasksApi]; only the three outbox endpoints are
     * exercised, the rest throw if a test ever wanders into them.
     */
    private class FakeApi(
        private val presignKey: String = "k",
        private val presignUrl: String = "https://put/url",
        private val noteError: Throwable? = null,
        private val photoError: Throwable? = null,
    ) : TasksApi {
        val noteRequests = mutableListOf<TripNoteRequest>()
        val presignRequests = mutableListOf<PhotoPresignRequest>()
        val confirmRequests = mutableListOf<PhotoConfirmRequest>()
        val standalonePresignRequests = mutableListOf<StandalonePhotoPresignRequest>()
        val standaloneConfirmRequests = mutableListOf<StandalonePhotoConfirmRequest>()

        override suspend fun addTripNote(body: TripNoteRequest): TripNoteResponse {
            noteError?.let { throw it }
            noteRequests += body
            return TripNoteResponse(ok = true, journalId = 1)
        }

        override suspend fun presignPhoto(body: PhotoPresignRequest): PhotoPresignResponse {
            presignRequests += body
            return PhotoPresignResponse(key = presignKey, uploadUrl = presignUrl)
        }

        override suspend fun addTripPhoto(body: PhotoConfirmRequest): PhotoConfirmResponse {
            photoError?.let { throw it }
            confirmRequests += body
            return PhotoConfirmResponse(ok = true, photoId = 1)
        }

        override suspend fun presignStandalonePhoto(
            body: StandalonePhotoPresignRequest,
        ): PhotoPresignResponse {
            standalonePresignRequests += body
            return PhotoPresignResponse(key = presignKey, uploadUrl = presignUrl)
        }

        override suspend fun addStandalonePhoto(
            body: StandalonePhotoConfirmRequest,
        ): PhotoConfirmResponse {
            photoError?.let { throw it }
            standaloneConfirmRequests += body
            return PhotoConfirmResponse(ok = true, photoId = 1)
        }

        // --- unused endpoints ---
        override suspend fun trackHabit(body: TrackHabitRequest): TrackHabitResponse = nope()
        override suspend fun trackHabitText(body: TrackHabitTextRequest): OkResponse = nope()
        override suspend fun listTodayTasks(date: String): TodayTasksResponse = nope()
        override suspend fun listBoardItems(): BoardItemsResponse = nope()
        override suspend fun addTodayTask(body: TaskTextRequest): OkResponse = nope()
        override suspend fun completeTodayTask(body: TaskCompleteRequest): OkResponse = nope()
        override suspend fun deleteTodayTask(body: TaskTextRequest): OkResponse = nope()
        override suspend fun listPlans(thread: String, pubDate: String): PlanListResponse = nope()
        override suspend fun startTrip(body: TripStartRequest): TripResponse = nope()
        override suspend fun stopTrip(body: TripStoryIdRequest): TripResponse = nope()
        override suspend fun updateTrip(body: TripUpdateRequest): TripResponse = nope()
        override suspend fun listTrips(page: Int, pageSize: Int): TripListResponse = nope()
        override suspend fun tripDetail(storyId: Long): TripDetailResponse = nope()
        override suspend fun photoOriginal(eventId: Long): PhotoOriginalResponse = nope()

        private fun nope(): Nothing = throw AssertionError("unexpected API call")
    }
}
