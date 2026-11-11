package org.polybrain.tasks.health.sync

import java.io.File
import java.io.IOException
import java.nio.file.Files
import kotlinx.coroutines.test.runTest
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.polybrain.tasks.health.data.AgendaResponse
import org.polybrain.tasks.health.data.BoardItemsResponse
import org.polybrain.tasks.health.data.HabitKeyword
import org.polybrain.tasks.health.data.HealthDataResponse
import org.polybrain.tasks.health.data.Outbox
import org.polybrain.tasks.health.data.OutboxItem
import org.polybrain.tasks.health.data.OkResponse
import org.polybrain.tasks.health.data.PhotoConfirmRequest
import org.polybrain.tasks.health.data.PhotoConfirmResponse
import org.polybrain.tasks.health.data.PhotoOriginalResponse
import org.polybrain.tasks.health.data.PhotoPresignRequest
import org.polybrain.tasks.health.data.PhotoPresignResponse
import org.polybrain.tasks.health.data.PlanItemRequest
import org.polybrain.tasks.health.data.PlanRef
import org.polybrain.tasks.health.data.PlanTextRequest
import org.polybrain.tasks.health.data.StandalonePhotoConfirmRequest
import org.polybrain.tasks.health.data.StandalonePhotoPresignRequest
import org.polybrain.tasks.health.data.Task
import org.polybrain.tasks.health.data.TaskCompleteRequest
import org.polybrain.tasks.health.data.TaskMoveRequest
import org.polybrain.tasks.health.data.TaskOp
import org.polybrain.tasks.health.data.TaskReopenRequest
import org.polybrain.tasks.health.data.TasksApi
import org.polybrain.tasks.health.data.TrackHabitRequest
import org.polybrain.tasks.health.data.TrackHabitResponse
import org.polybrain.tasks.health.data.TrackHabitTextRequest
import org.polybrain.tasks.health.data.TripDetailResponse
import org.polybrain.tasks.health.data.TripListResponse
import org.polybrain.tasks.health.data.TripNoteRequest
import org.polybrain.tasks.health.data.TripNoteResponse
import org.polybrain.tasks.health.data.TripResponse
import org.polybrain.tasks.health.data.TripShareResponse
import org.polybrain.tasks.health.data.TripStartRequest
import org.polybrain.tasks.health.data.TripStopRequest
import org.polybrain.tasks.health.data.TripStoryIdRequest
import org.polybrain.tasks.health.data.TripUpdateRequest
import org.polybrain.tasks.health.data.UnscheduledTaskRequest
import org.polybrain.tasks.health.data.UnscheduledTaskResponse
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
        val item = outbox.enqueuePhoto(2L, "cap", "t", "image/jpeg", byteArrayOf(1, 2, 3))!!
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
        val base = outbox.enqueuePhoto(2L, "cap", "t", "image/jpeg", byteArrayOf(1, 2, 3))!!
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
        val item = outbox.enqueuePhoto(null, "cap", "t", "image/jpeg", byteArrayOf(9))!!
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
        val item = outbox.enqueuePhoto(1L, "c", "t", "image/jpeg", byteArrayOf(7))!!
        // Delete the bytes file but keep the item (simulates corruption).
        outbox.photoFile(item)!!.delete()
        val api = FakeApi()
        val outcome = OutboxDrainer.process(item, api, outbox, noopPut)
        assertTrue(outcome is OutboxDrainer.Outcome.Permanent)
        assertEquals(0, api.presignRequests.size)
    }

    @Test
    fun `a failed confirm keeps what the upload achieved`() = runTest {
        val item = outbox.enqueuePhoto(2L, "cap", "t", "image/jpeg", byteArrayOf(1, 2, 3))!!
        val api = FakeApi(presignKey = "trips/2/k.jpg", photoError = IOException("gone"))

        val outcome = OutboxDrainer.process(item, api, outbox, noopPut)

        // The outcome carries the uploaded flag, so the bookkeeping that
        // follows (attempts, last error) doesn't write the item back without it.
        assertTrue(outcome is OutboxDrainer.Outcome.Retry)
        assertTrue(outcome.item.uploaded)
        assertEquals("trips/2/k.jpg", outcome.item.presignedKey)
    }

    // --- task calls ---

    private val day = "2026-11-11"
    private val bank = Task(id = "t-bank", text = "call bank")
    private val plain = Task(text = "written long ago")

    private fun queue(
        type: TaskOp.Type,
        task: Task,
        toDate: String? = null,
        note: String? = null,
        storyId: Long? = null,
        boardId: Long? = null,
        itemId: String? = null,
    ): OutboxItem = outbox.enqueueTask(
        TaskOp(type, task, day, toDate, note, storyId, boardId, itemId),
        "2026-11-11T21:30:00+01:00",
    )

    private suspend fun send(item: OutboxItem, api: FakeApi) =
        OutboxDrainer.process(item, api, outbox, noopPut)

    @Test
    fun `a tick is sent once whatever is retried`() = runTest {
        val item = queue(TaskOp.Type.COMPLETE, bank, note = "sorted", storyId = 4L)
        val api = FakeApi()

        assertTrue(send(item, api) is OutboxDrainer.Outcome.Sent)

        val (id, body) = api.completions.single()
        assertEquals("t-bank", id)
        assertEquals(
            TaskCompleteRequest(
                day = day,
                // The moment of the tap, not of the delivery.
                at = "2026-11-11T21:30:00+01:00",
                note = "sorted",
                storyId = 4L,
                idempotencyKey = item.id,
            ),
            body,
        )
    }

    @Test
    fun `an untick takes back the step the user saw`() = runTest {
        val api = FakeApi()

        send(queue(TaskOp.Type.REOPEN, bank.copy(done = true, doneCount = 1)), api)

        assertEquals(listOf("reopen t-bank from 1"), api.calls)
    }

    @Test
    fun `a typed task is planned by its text, one with an id by its id`() = runTest {
        val api = FakeApi()

        send(queue(TaskOp.Type.PLAN, Task(text = "buy milk")), api)
        send(queue(TaskOp.Type.PLAN, bank), api)
        send(queue(TaskOp.Type.PLAN_ITEM, Task(text = "water plants"), boardId = 12, itemId = "i-1"), api)

        assertEquals(
            listOf(
                "planText buy milk on $day",
                "plan t-bank on $day",
                "planItem 12/i-1 on $day",
            ),
            api.calls,
        )
    }

    @Test
    fun `a line without an id gets one by being planned where it is`() = runTest {
        val item = queue(TaskOp.Type.MOVE, plain, toDate = "2026-11-12")
        val api = FakeApi()

        val outcome = send(item, api)

        assertTrue(outcome is OutboxDrainer.Outcome.Sent)
        assertEquals(
            listOf(
                "planText written long ago on $day",
                "move id-of-written long ago from $day to 2026-11-12",
            ),
            api.calls,
        )
    }

    @Test
    fun `the id it got is kept for the retry`() = runTest {
        // Moved, the line is no longer on the plan its text would be looked
        // up on: a retry must name the task it named the first time.
        val item = queue(TaskOp.Type.MOVE, plain, toDate = "2026-11-12")
        val api = FakeApi(failing = { if (it.startsWith("move")) IOException("lost") else null })

        val outcome = send(item, api)

        assertTrue(outcome is OutboxDrainer.Outcome.Retry)
        assertEquals("id-of-written long ago", outcome.item.task!!.task.id)
        assertEquals("id-of-written long ago", outbox.tasks().single().task!!.task.id)

        val again = FakeApi()
        assertTrue(send(outbox.tasks().single(), again) is OutboxDrainer.Outcome.Sent)
        assertEquals(
            listOf("move id-of-written long ago from $day to 2026-11-12"),
            again.calls,
        )
    }

    @Test
    fun `removing a task that is gone already is done`() = runTest {
        val gone = FakeApi(unplanCode = 404)
        assertTrue(send(queue(TaskOp.Type.UNPLAN, bank), gone) is OutboxDrainer.Outcome.Sent)
        assertEquals(listOf("unplan t-bank on $day"), gone.calls)

        val down = FakeApi(unplanCode = 503)
        assertTrue(send(queue(TaskOp.Type.UNPLAN, bank), down) is OutboxDrainer.Outcome.Retry)

        val refused = FakeApi(unplanCode = 400)
        assertTrue(
            send(queue(TaskOp.Type.UNPLAN, bank), refused) is OutboxDrainer.Outcome.Permanent
        )
    }

    @Test
    fun `a refused task call is permanent and a lost one is retried`() = runTest {
        val item = queue(TaskOp.Type.COMPLETE, bank, storyId = 4L)

        // 409: the trip it was saved to is stopped.
        assertTrue(
            send(item, FakeApi(failing = { httpException(409) }))
                is OutboxDrainer.Outcome.Permanent
        )
        assertTrue(
            send(item, FakeApi(failing = { IOException("offline") }))
                is OutboxDrainer.Outcome.Retry
        )
    }

    // --- a pass over the whole queue ---

    @Test
    fun `task calls go before trip writes, in their own order`() = runTest {
        outbox.enqueueNote(5L, "a note", "t")
        queue(TaskOp.Type.COMPLETE, bank)
        queue(TaskOp.Type.REOPEN, bank.copy(done = true, doneCount = 1))
        val api = FakeApi()

        val retry = OutboxDrainer.drain(outbox, api, noopPut)

        assertFalse(retry)
        assertEquals(listOf("complete t-bank", "reopen t-bank from 1", "note a note"), api.calls)
        assertTrue(outbox.all().isEmpty())
    }

    @Test
    fun `a task call that has to wait holds back those after it`() = runTest {
        // Sending the untick alone would leave the task ticked for good once
        // the tick arrives after it.
        outbox.enqueueNote(5L, "a note", "t")
        queue(TaskOp.Type.COMPLETE, bank)
        queue(TaskOp.Type.REOPEN, bank.copy(done = true, doneCount = 1))
        val api = FakeApi(failing = { if (it.startsWith("complete")) httpException(503) else null })

        val retry = OutboxDrainer.drain(outbox, api, noopPut)

        assertTrue(retry)
        // The trip note is not held back by a task.
        assertEquals(listOf("note a note"), api.calls)
        val left = outbox.tasks()
        assertEquals(
            listOf(TaskOp.Type.COMPLETE, TaskOp.Type.REOPEN),
            left.map { it.task!!.type },
        )
        assertEquals(listOf(1, 0), left.map { it.attempts })
        assertEquals("HTTP 503", left[0].lastError)
    }

    @Test
    fun `a refused call is kept for the user and the rest goes on`() = runTest {
        queue(TaskOp.Type.COMPLETE, bank, storyId = 4L)
        queue(TaskOp.Type.PLAN, Task(text = "buy milk"))
        val api = FakeApi(failing = { if (it.startsWith("complete")) httpException(409) else null })

        assertFalse(OutboxDrainer.drain(outbox, api, noopPut))

        val refused = outbox.tasks().single()
        assertTrue(refused.failedPermanently)
        assertEquals("HTTP 409", refused.lastError)
        assertEquals(listOf("planText buy milk on $day"), api.calls)

        // Not tried again until the user says so.
        assertFalse(OutboxDrainer.drain(outbox, api, noopPut))
        assertEquals(1, api.calls.size)
    }

    /**
     * Fake covering the whole [TasksApi]; only the endpoints the outbox uses
     * are exercised, the rest throw if a test ever wanders into them.
     *
     * Task calls and trip notes are logged in [calls], one line each;
     * [failing] may refuse a call by that line.
     */
    private class FakeApi(
        private val presignKey: String = "k",
        private val presignUrl: String = "https://put/url",
        private val noteError: Throwable? = null,
        private val photoError: Throwable? = null,
        private val failing: (String) -> Throwable? = { null },
        private val unplanCode: Int = 204,
    ) : TasksApi {
        val calls = mutableListOf<String>()
        val completions = mutableListOf<Pair<String, TaskCompleteRequest>>()

        private fun call(line: String) {
            failing(line)?.let { throw it }
            calls += line
        }

        val noteRequests = mutableListOf<TripNoteRequest>()
        val presignRequests = mutableListOf<PhotoPresignRequest>()
        val confirmRequests = mutableListOf<PhotoConfirmRequest>()
        val standalonePresignRequests = mutableListOf<StandalonePhotoPresignRequest>()
        val standaloneConfirmRequests = mutableListOf<StandalonePhotoConfirmRequest>()

        override suspend fun addTripNote(body: TripNoteRequest): TripNoteResponse {
            noteError?.let { throw it }
            call("note ${body.comment}")
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

        override suspend fun planText(body: PlanTextRequest): Task {
            call("planText ${body.text} on ${body.date}")
            return Task(id = "id-of-${body.text}", text = body.text)
        }

        override suspend fun planItem(body: PlanItemRequest): Task {
            call("planItem ${body.boardId}/${body.itemId} on ${body.date}")
            return Task(id = "id-of-${body.itemId}", text = "")
        }

        override suspend fun planTask(id: String, body: PlanRef): Task {
            call("plan $id on ${body.date}")
            return Task(id = id, text = "")
        }

        override suspend fun unplanTask(id: String, body: PlanRef): Response<Unit> {
            call("unplan $id on ${body.date}")
            return if (unplanCode in 200..299) {
                Response.success(unplanCode, Unit)
            } else {
                Response.error(unplanCode, "err".toResponseBody(null))
            }
        }

        override suspend fun moveTask(id: String, body: TaskMoveRequest): Task {
            call("move $id from ${body.fromDate} to ${body.toDate}")
            return Task(id = id, text = "")
        }

        override suspend fun completeTask(id: String, body: TaskCompleteRequest): Task {
            call("complete $id")
            completions += id to body
            return Task(id = id, text = "")
        }

        override suspend fun reopenTask(id: String, body: TaskReopenRequest): Task {
            call("reopen $id from ${body.doneCount}")
            return Task(id = id, text = "")
        }

        // --- unused endpoints ---
        override suspend fun trackHabit(body: TrackHabitRequest): TrackHabitResponse = nope()
        override suspend fun trackHabitText(body: TrackHabitTextRequest): OkResponse = nope()
        override suspend fun listHabitKeywords(date: String): List<HabitKeyword> = nope()
        override suspend fun healthData(): HealthDataResponse = nope()
        override suspend fun agenda(date: String): AgendaResponse = nope()
        override suspend fun listBoardItems(): BoardItemsResponse = nope()
        override suspend fun appendUnscheduledTask(
            body: UnscheduledTaskRequest,
        ): UnscheduledTaskResponse = nope()
        override suspend fun startTrip(body: TripStartRequest): TripResponse = nope()
        override suspend fun stopTrip(body: TripStopRequest): TripResponse = nope()
        override suspend fun updateTrip(body: TripUpdateRequest): TripResponse = nope()
        override suspend fun shareTrip(body: TripStoryIdRequest): TripShareResponse = nope()
        override suspend fun revokeTripShare(body: TripStoryIdRequest): TripShareResponse = nope()
        override suspend fun listTrips(page: Int, pageSize: Int): TripListResponse = nope()
        override suspend fun tripDetail(storyId: Long): TripDetailResponse = nope()
        override suspend fun photoOriginal(eventId: Long): PhotoOriginalResponse = nope()

        private fun nope(): Nothing = throw AssertionError("unexpected API call")
    }
}
