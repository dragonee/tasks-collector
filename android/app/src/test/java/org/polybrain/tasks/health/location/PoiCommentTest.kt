package org.polybrain.tasks.health.location

import org.junit.Assert.assertEquals
import org.junit.Test

class PoiCommentTest {

    @Test
    fun `no fix returns the trimmed text`() {
        assertEquals("hello", composeComment(null, "  hello  "))
    }

    @Test
    fun `no fix and blank text returns empty`() {
        assertEquals("", composeComment(null, "   "))
    }

    @Test
    fun `a fix prepends a six-decimal poi line above the text`() {
        val fix = LocationFix(40.7128, -74.006, 5f)
        assertEquals(
            "#poi lat=40.712800 lng=-74.006000\nat the pier",
            composeComment(fix, "at the pier"),
        )
    }

    @Test
    fun `a fix with blank text is just the poi line`() {
        val fix = LocationFix(1.5, 2.5, null)
        assertEquals("#poi lat=1.500000 lng=2.500000", composeComment(fix, "  "))
    }
}
