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

class BreadcrumbStoreTest {

    private lateinit var file: File
    private lateinit var store: BreadcrumbStore

    @Before
    fun setUp() {
        val dir = Files.createTempDirectory("breadcrumb-test").toFile()
        file = File(dir, "breadcrumbs.log")
        store = BreadcrumbStore(file)
    }

    @After
    fun tearDown() {
        file.parentFile?.deleteRecursively()
    }

    @Test
    fun `append then all round-trips and sorts by time`() {
        store.append(Breadcrumb(t = 300, lat = 3.0, lng = 3.0))
        store.append(Breadcrumb(t = 100, lat = 1.0, lng = 1.0, acc = 5f))
        store.append(Breadcrumb(t = 200, lat = 2.0, lng = 2.0))
        val all = store.all()
        assertEquals(listOf(100L, 200L, 300L), all.map { it.t })
        assertEquals(5f, all.first().acc)
    }

    @Test
    fun `all is empty when nothing written`() {
        assertTrue(store.all().isEmpty())
    }

    @Test
    fun `lastAtOrBefore and firstAtOrAfter respect boundaries`() {
        store.append(Breadcrumb(t = 100, lat = 1.0, lng = 1.0))
        store.append(Breadcrumb(t = 200, lat = 2.0, lng = 2.0))
        store.append(Breadcrumb(t = 300, lat = 3.0, lng = 3.0))
        assertEquals(200L, store.lastAtOrBefore(250)?.t)
        assertEquals(200L, store.lastAtOrBefore(200)?.t) // inclusive
        assertEquals(300L, store.firstAtOrAfter(250)?.t)
        assertEquals(300L, store.firstAtOrAfter(300)?.t) // inclusive
        assertNull(store.lastAtOrBefore(50))
        assertNull(store.firstAtOrAfter(400))
    }

    @Test
    fun `a torn final line is skipped not fatal`() {
        store.append(Breadcrumb(t = 100, lat = 1.0, lng = 1.0))
        file.appendText("{not valid json")
        assertEquals(1, store.all().size)
    }

    @Test
    fun `clear removes the log`() {
        store.append(Breadcrumb(t = 100, lat = 1.0, lng = 1.0))
        store.clear()
        assertFalse(file.exists())
        assertTrue(store.all().isEmpty())
    }
}
