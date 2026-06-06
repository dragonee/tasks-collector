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
        val item = outbox.enqueueNote(7L, "#poi lat=1.0 lng=2.0\nhi", "2026-06-06T10:00:00Z")
        val all = outbox.all()
        assertEquals(1, all.size)
        assertEquals(item.id, all[0].id)
        assertEquals(OutboxItem.Kind.NOTE, all[0].kind)
        assertEquals(7L, all[0].storyId)
        assertEquals("#poi lat=1.0 lng=2.0\nhi", all[0].comment)
    }

    @Test
    fun `enqueuePhoto writes the photo bytes alongside the item`() {
        val bytes = byteArrayOf(1, 2, 3, 4, 5)
        val item = outbox.enqueuePhoto(3L, "caption", "2026-06-06T10:00:00Z", "image/jpeg", bytes)
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
        val item = outbox.enqueuePhoto(1L, "c", "t", "image/png", byteArrayOf(9))
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
}
