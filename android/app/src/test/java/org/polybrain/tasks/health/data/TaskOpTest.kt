package org.polybrain.tasks.health.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** What the Today lists show while task calls wait in the outbox. */
class TaskOpTest {

    private val day = "2026-11-11"
    private val tomorrow = "2026-11-12"

    private val bank = Task(id = "t-bank", text = "call bank")
    private val counted = Task(
        id = "t-x", text = "Do x (3)", display = "Do x (2/3)", total = 3, doneCount = 1,
    )
    private val plain = Task(text = "written long ago")

    private fun op(
        type: TaskOp.Type,
        task: Task,
        date: String = day,
        toDate: String? = null,
    ) = TaskOp(type, task, date, toDate = toDate)

    @Test
    fun `a task typed in shows on its day only`() {
        val typed = op(TaskOp.Type.PLAN, Task(text = "buy milk"))

        assertEquals(listOf(bank, Task(text = "buy milk")), listOf(bank).withPending(listOf(typed), day))
        assertEquals(listOf(bank), listOf(bank).withPending(listOf(typed), tomorrow))
        // The week's plan is no day's list.
        assertEquals(listOf(bank), listOf(bank).withPending(listOf(typed), null))
    }

    @Test
    fun `planning what is on the day already adds nothing`() {
        val again = listOf(
            op(TaskOp.Type.PLAN, bank),
            op(TaskOp.Type.PLAN, plain),
            op(TaskOp.Type.PLAN_ITEM, Task(text = "call bank")),
        )

        assertEquals(listOf(bank, plain), listOf(bank, plain).withPending(again, day))
    }

    @Test
    fun `a tick shows at once, and an untick after it`() {
        val tick = op(TaskOp.Type.COMPLETE, bank)
        val ticked = listOf(bank).withPending(listOf(tick), day).single()

        assertTrue(ticked.done)
        assertEquals(1, ticked.doneCount)

        val untick = op(TaskOp.Type.REOPEN, ticked)
        val open = listOf(bank).withPending(listOf(tick, untick), day).single()

        assertFalse(open.done)
        assertEquals(0, open.doneCount)
    }

    @Test
    fun `a counted task goes a step at a time and shows the step it is on`() {
        val step = op(TaskOp.Type.COMPLETE, counted)

        val two = listOf(counted).withPending(listOf(step), day).single()
        assertEquals(Triple(2, false, "Do x (3/3)"), Triple(two.doneCount, two.done, two.display))

        val three = listOf(counted).withPending(listOf(step, step), day).single()
        assertEquals(Triple(3, true, "Do x (3/3)"), Triple(three.doneCount, three.done, three.display))

        // "Add another" goes past the total; "Reset" takes one back.
        val four = listOf(counted).withPending(listOf(step, step, step), day).single()
        assertEquals(4, four.doneCount)
        val back = listOf(counted)
            .withPending(listOf(step, step, op(TaskOp.Type.REOPEN, three)), day)
            .single()
        assertEquals(Triple(2, false, "Do x (3/3)"), Triple(back.doneCount, back.done, back.display))
    }

    @Test
    fun `a task without steps is done once`() {
        val done = bank.copy(done = true, doneCount = 1)

        assertEquals(done, listOf(done).withPending(listOf(op(TaskOp.Type.COMPLETE, done)), day).single())
    }

    @Test
    fun `a task ticked on the day is done on the week's plan too`() {
        val ticked = listOf(bank, counted).withPending(listOf(op(TaskOp.Type.COMPLETE, bank)), null)

        assertEquals(listOf(true, false), ticked.map { it.done })
    }

    @Test
    fun `a plain line is named by its text on its own day`() {
        val tick = op(TaskOp.Type.COMPLETE, plain)

        assertTrue(listOf(plain).withPending(listOf(tick), day).single().done)
        // The same words on another day's plan are another line.
        assertFalse(listOf(plain).withPending(listOf(tick), tomorrow).single().done)
        assertFalse(listOf(plain).withPending(listOf(tick), null).single().done)
    }

    @Test
    fun `a line that got its id meanwhile is still the one meant`() {
        // The drainer learned the id (the call names it now); the list in
        // hand is from before. And the other way round.
        val named = op(TaskOp.Type.COMPLETE, plain.copy(id = "t-new"))
        assertTrue(listOf(plain).withPending(listOf(named), day).single().done)

        val byText = op(TaskOp.Type.COMPLETE, plain)
        assertTrue(listOf(plain.copy(id = "t-new")).withPending(listOf(byText), day).single().done)
    }

    @Test
    fun `a task typed in and ticked before either was sent`() {
        val typed = Task(text = "buy milk")
        val ops = listOf(op(TaskOp.Type.PLAN, typed), op(TaskOp.Type.COMPLETE, typed))

        assertTrue(emptyList<Task>().withPending(ops, day).single().done)
    }

    @Test
    fun `moved to tomorrow it leaves the day and shows on the next`() {
        val move = op(TaskOp.Type.MOVE, bank, toDate = tomorrow)

        assertEquals(listOf(counted), listOf(bank, counted).withPending(listOf(move), day))
        assertEquals(listOf(bank), emptyList<Task>().withPending(listOf(move), tomorrow))
        assertEquals(listOf(bank), listOf(bank).withPending(listOf(move), tomorrow))
    }

    @Test
    fun `removed it is off that day's list`() {
        val remove = op(TaskOp.Type.UNPLAN, bank)

        assertEquals(listOf(counted), listOf(bank, counted).withPending(listOf(remove), day))
        assertEquals(listOf(bank), listOf(bank).withPending(listOf(remove), tomorrow))
    }

    // --- QueuedTaskOps: which calls a list still has to show ---

    private fun item(id: String, createdAt: Long, failed: Boolean = false) = OutboxItem(
        id = id,
        kind = OutboxItem.Kind.TASK,
        storyId = null,
        comment = "",
        published = "t",
        createdAt = createdAt,
        task = op(TaskOp.Type.COMPLETE, bank),
        failedPermanently = failed,
    )

    @Test
    fun `a call that was sent is shown until a list fetched after it is in`() {
        val queue = QueuedTaskOps()
        val a = item("a", 1)
        val b = item("b", 2)

        assertFalse(queue.sync(listOf(a, b)))
        assertEquals(emptySet<String>(), queue.sent)

        // a was sent: worth a fetch, and still shown meanwhile.
        assertTrue(queue.sync(listOf(b)))
        assertEquals(listOf(a, b), queue.items)
        val covered = queue.sent
        assertEquals(setOf("a"), covered)
        // Nothing new since: no second fetch for the same call.
        assertFalse(queue.sync(listOf(b)))

        // b is sent while that fetch is on its way: the answer may not have it.
        assertTrue(queue.sync(emptyList()))
        queue.fetched(covered)

        assertEquals(listOf(b), queue.items)
        assertEquals(setOf("b"), queue.sent)
        assertFalse(queue.sync(emptyList()))
        queue.fetched(queue.sent)
        assertEquals(emptyList<OutboxItem>(), queue.items)
    }

    @Test
    fun `the outbox says how a waiting call is doing`() {
        val queue = QueuedTaskOps()
        queue.sync(listOf(item("a", 1)))

        assertFalse(queue.sync(listOf(item("a", 1, failed = true), item("b", 2))))

        assertEquals(listOf(true, false), queue.items.map { it.failedPermanently })
    }

    @Test
    fun `a call thrown away is not one that was sent`() {
        val queue = QueuedTaskOps()
        queue.sync(listOf(item("a", 1, failed = true)))

        queue.discard("a")

        assertFalse(queue.sync(emptyList()))
        assertEquals(emptyList<OutboxItem>(), queue.items)
    }
}
