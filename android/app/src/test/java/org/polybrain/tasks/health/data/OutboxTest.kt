package org.polybrain.tasks.health.data

import java.io.File
import java.nio.file.Files
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.polybrain.tasks.health.location.LocationFix

class OutboxTest {

    private lateinit var dir: File
    private lateinit var outbox: Outbox

    @Before
    fun setUp() {
        dir = Files.createTempDirectory("outbox-test").toFile()
        outbox = Outbox(dir)
    }

    @After
    fun tearDown() {
        dir.deleteRecursively()
    }

    @Test
    fun `enqueueNote persists a retrievable item`() {
        val item = outbox.enqueueNote(7L, "hi", "2026-06-06T10:00:00Z")
        val all = outbox.all()
        assertEquals(1, all.size)
        assertEquals(item.id, all[0].id)
        assertEquals(OutboxItem.Kind.NOTE, all[0].kind)
        assertEquals(7L, all[0].storyId)
        assertEquals("hi", all[0].comment)
    }

    @Test
    fun `a note keeps the place it was made at`() {
        val item = outbox.enqueueNote(7L, "", "t", LocationFix(40.7128, -74.006, 5f))

        val read = outbox.all().single()
        assertEquals(item, read)
        assertEquals(40.7128, read.lat!!, 0.0)
        assertEquals(-74.006, read.lng!!, 0.0)
        assertEquals(5f, read.acc!!, 0f)
        // The place is not written into the text.
        assertEquals("", read.comment)
    }

    @Test
    fun `a photo keeps the place it was taken at, with or without its accuracy`() {
        val fix = LocationFix(1.5, 2.5, null)
        outbox.enqueuePhoto(3L, "cap", "t", "image/jpeg", byteArrayOf(1), fix)
        outbox.enqueuePhoto(null, "", "t", "image/jpeg", byteArrayOf(2), fix)

        for (read in outbox.all()) {
            assertEquals(1.5, read.lat!!, 0.0)
            assertEquals(2.5, read.lng!!, 0.0)
            assertNull(read.acc)
        }
    }

    @Test
    fun `an item sent without a location has none`() {
        outbox.enqueueNote(1L, "x", "t")
        outbox.enqueuePhoto(1L, "c", "t", "image/jpeg", byteArrayOf(1))

        for (read in outbox.all()) {
            assertNull(read.lat)
            assertNull(read.lng)
            assertNull(read.acc)
        }
    }

    @Test
    fun `an item queued by an older build still reads, its place left in the comment`() {
        // As a build from before lat, lng and acc wrote it.
        File(dir, "0000000000000001-0b7c51d2.json").writeText(
            """
            {"id": "0b7c51d2-6f1e-4c55-9d1a-0f6f3b2f9a10", "kind": "NOTE",
             "storyId": 3, "comment": "#poi lat=1.000000 lng=2.000000\nhi",
             "published": "2026-06-06T10:00:00Z", "createdAt": 1,
             "contentType": null, "photoFile": null, "contentHash": null,
             "presignedKey": null, "uploaded": false, "task": null,
             "attempts": 2, "lastError": "HTTP 503", "failedPermanently": false}
            """,
        )

        val read = outbox.forStory(3L).single()
        assertEquals("#poi lat=1.000000 lng=2.000000\nhi", read.comment)
        assertNull(read.lat)
        assertNull(read.lng)
        assertEquals(2, read.attempts)
    }

    @Test
    fun `enqueuePhoto writes the photo bytes alongside the item`() {
        val bytes = byteArrayOf(1, 2, 3, 4, 5)
        val item = outbox.enqueuePhoto(3L, "caption", "2026-06-06T10:00:00Z", "image/jpeg", bytes)!!
        assertTrue(item.isPhoto)
        assertEquals("image/jpeg", item.contentType)
        assertTrue(outbox.photoFile(item)!!.name.endsWith(".jpg"))
        assertTrue(bytes.contentEquals(outbox.photoBytes(item)))
    }

    @Test
    fun `all returns items oldest first`() {
        // createdAt is the filename prefix; force distinct timestamps by spacing.
        val a = outbox.enqueueNote(1L, "first", "t1")
        Thread.sleep(2)
        val b = outbox.enqueueNote(1L, "second", "t2")
        val ids = outbox.all().map { it.id }
        assertEquals(listOf(a.id, b.id), ids)
    }

    @Test
    fun `forStory filters by story`() {
        outbox.enqueueNote(1L, "a", "t")
        outbox.enqueueNote(2L, "b", "t")
        assertEquals(1, outbox.forStory(1L).size)
        assertEquals(2L, outbox.forStory(2L).single().storyId)
    }

    @Test
    fun `enqueuePhoto with null story is a standalone photo`() {
        val bytes = byteArrayOf(4, 2)
        val item = outbox.enqueuePhoto(null, "cap", "2026-06-06T10:00:00Z", "image/jpeg", bytes)!!
        assertNull(item.storyId)
        val reloaded = outbox.all().single()
        assertNull(reloaded.storyId)
        assertTrue(bytes.contentEquals(outbox.photoBytes(reloaded)))
        // A storyless photo never shows under any trip, but is still drained.
        assertTrue(outbox.forStory(0L).isEmpty())
        assertEquals(1, outbox.all().size)
    }

    @Test
    fun `standalone returns only storyless items`() {
        outbox.enqueueNote(1L, "trip note", "t")
        outbox.enqueuePhoto(1L, "trip photo", "t", "image/jpeg", byteArrayOf(1))
        val solo = outbox.enqueuePhoto(null, "standalone", "t", "image/jpeg", byteArrayOf(2))!!
        assertEquals(listOf(solo.id), outbox.standalone().map { it.id })
    }

    @Test
    fun `task calls are kept in the order they were made`() {
        // Queued within the same millisecond more often than not; a random
        // id must not decide which comes first.
        val texts = (1..20).map { "task $it" }
        for (text in texts) {
            outbox.enqueueTask(TaskOp(TaskOp.Type.PLAN, Task(text = text), "2026-11-11"), "t")
        }

        assertEquals(texts, outbox.tasks().map { it.task!!.task.text })
        assertEquals(texts, outbox.all().map { it.task!!.task.text })
    }

    @Test
    fun `a task call is its own kind of item`() {
        outbox.enqueueNote(1L, "trip note", "t")
        val solo = outbox.enqueuePhoto(null, "standalone", "t", "image/jpeg", byteArrayOf(2))!!
        val call = outbox.enqueueTask(
            TaskOp(
                TaskOp.Type.COMPLETE,
                Task(id = "t-1", text = "call bank"),
                "2026-11-11",
                note = "sorted",
                storyId = 4L,
            ),
            "2026-11-11T10:00:00+01:00",
        )

        val read = outbox.tasks().single()
        assertEquals(call, read)
        assertEquals(OutboxItem.Kind.TASK, read.kind)
        assertEquals("sorted", read.task!!.note)
        // Saved to a trip or not, it is no trip write and no standalone photo.
        assertNull(read.storyId)
        assertTrue(outbox.forStory(4L).isEmpty())
        assertEquals(listOf(solo.id), outbox.standalone().map { it.id })
    }

    @Test
    fun `update rewrites the same file in place`() {
        val item = outbox.enqueueNote(1L, "x", "t")
        outbox.update(item.copy(attempts = 3, lastError = "boom"))
        val reloaded = outbox.all().single()
        assertEquals(item.id, reloaded.id)
        assertEquals(3, reloaded.attempts)
        assertEquals("boom", reloaded.lastError)
        assertEquals(1, outbox.all().size) // no duplicate file
    }

    @Test
    fun `remove deletes the json and the photo file`() {
        val item = outbox.enqueuePhoto(1L, "c", "t", "image/png", byteArrayOf(9))!!
        val photo = outbox.photoFile(item)!!
        assertTrue(photo.exists())
        outbox.remove(item)
        assertTrue(outbox.all().isEmpty())
        assertFalse(photo.exists())
    }

    @Test
    fun `photoBytes is null for a note`() {
        val item = outbox.enqueueNote(1L, "x", "t")
        assertNull(outbox.photoBytes(item))
    }

    @Test
    fun `enqueuePhoto skips an identical image already queued for the story`() {
        val bytes = byteArrayOf(1, 2, 3)
        val first = outbox.enqueuePhoto(1L, "a", "t1", "image/jpeg", bytes)
        // Same bytes -> same content hash -> deduped (returns null, writes nothing).
        val second = outbox.enqueuePhoto(1L, "b", "t2", "image/jpeg", bytes)
        assertTrue(first != null)
        assertNull(second)
        assertEquals(1, outbox.forStory(1L).size)
    }

    @Test
    fun `enqueuePhoto dedups per scope, not across stories`() {
        val bytes = byteArrayOf(7, 8, 9)
        assertTrue(outbox.enqueuePhoto(1L, "a", "t", "image/jpeg", bytes) != null)
        // Same image, different trip -> allowed.
        assertTrue(outbox.enqueuePhoto(2L, "a", "t", "image/jpeg", bytes) != null)
        assertEquals(1, outbox.forStory(1L).size)
        assertEquals(1, outbox.forStory(2L).size)
    }

    @Test
    fun `enqueuePhoto re-enqueues an image whose prior copy failed permanently`() {
        val bytes = byteArrayOf(5, 5, 5)
        val first = outbox.enqueuePhoto(1L, "a", "t", "image/jpeg", bytes)!!
        outbox.update(first.copy(failedPermanently = true))
        // A permanently-failed copy must not block a fresh attempt.
        val retry = outbox.enqueuePhoto(1L, "a", "t", "image/jpeg", bytes)
        assertTrue(retry != null)
    }
}
