package org.polybrain.tasks.health.data

import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class TaskTest {

    // As TasksClient configures it.
    private val json = Json {
        ignoreUnknownKeys = true
        encodeDefaults = true
    }

    private fun task(id: String?, text: String, done: Boolean = false) =
        Task(id = id, text = text, done = done)

    @Test
    fun `an agenda as the server sends it`() {
        val agenda = json.decodeFromString<AgendaResponse>(
            """
            {"date": "2026-11-11",
             "daily": {"thread": "Daily", "pub_date": "2026-11-11", "tasks": [
               {"id": "7b1e", "anchor": "91bd0a44", "text": "Do x (3)",
                "display": "Do x (2/3)", "done": false, "mark": null, "total": 3,
                "done_count": 1, "completed_at": null,
                "board": {"id": 12, "item_id": "i-1", "thread": "Inbox"},
                "plans": [{"thread": "Daily", "pub_date": "2026-11-11"}]}]},
             "weekly": {"thread": "Weekly", "pub_date": "2026-11-15", "tasks": [
               {"id": null, "anchor": null, "text": "a plain line",
                "display": "a plain line", "done": true, "mark": "~", "total": 1,
                "done_count": 1, "completed_at": null, "board": null, "plans": []}]},
             "monthly": {"thread": "big-picture", "pub_date": "2026-11-30", "tasks": []}}
            """,
        )

        val counted = agenda.daily.tasks.single()
        assertEquals("7b1e", counted.id)
        assertEquals("Do x (2/3)", counted.shown)
        assertEquals(3, counted.total)
        assertEquals(1, counted.doneCount)
        assertFalse(counted.isCountedAndDone)

        val plain = agenda.weekly.tasks.single()
        assertNull(plain.id)
        assertEquals("text:a plain line", plain.key)
        assertEquals("~", plain.mark)
        assertTrue(agenda.monthly.tasks.isEmpty())
    }

    @Test
    fun `a row is told from the others by its task`() {
        // Two tasks may read the same; a plain line has only its text.
        assertEquals("a", task("a", "same").key)
        assertEquals("b", task("b", "same").key)
        assertEquals("text:same", task(null, "same").key)
    }

    @Test
    fun `only a counted task with all its steps done offers another`() {
        assertTrue(Task(text = "Do x (3)", total = 3, doneCount = 3).isCountedAndDone)
        assertTrue(Task(text = "Do x (3)", total = 3, doneCount = 4).isCountedAndDone)
        assertFalse(Task(text = "Do x (3)", total = 3, doneCount = 2).isCountedAndDone)
        assertFalse(Task(text = "plain", total = 1, doneCount = 1).isCountedAndDone)
    }

    @Test
    fun `a task of the week done on another day is not offered again`() {
        val week = listOf(
            task("done-yesterday", "write report", done = true),
            task("on-today", "call bank"),
            task("left", "read a book"),
            task(null, "an old plain line"),
        )
        val today = listOf(task("on-today", "call bank"), task("other", "buy bread"))

        assertEquals(
            listOf("read a book", "an old plain line"),
            weekPlanLeft(week, today).map { it.text },
        )
    }

    @Test
    fun `a request to plan what was typed names no board item`() {
        // The server wants either text or an item; nulls would be sent too.
        assertEquals(
            """{"text":"call bank","date":"2026-11-11","thread":"Daily"}""",
            json.encodeToString(
                PlanTextRequest.serializer(),
                PlanTextRequest("call bank", "2026-11-11"),
            ),
        )
        assertEquals(
            """{"board_id":12,"item_id":"i-1","date":"2026-11-11","thread":"Daily"}""",
            json.encodeToString(
                PlanItemRequest.serializer(),
                PlanItemRequest(12, "i-1", "2026-11-11"),
            ),
        )
    }
}
