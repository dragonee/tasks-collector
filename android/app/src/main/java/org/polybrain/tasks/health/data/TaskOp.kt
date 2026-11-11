package org.polybrain.tasks.health.data

import kotlinx.serialization.Serializable

/**
 * One thing done to a task on the phone, queued in the [Outbox] until the
 * server has it (see `sync/OutboxDrainer`). Until then the lists show it done
 * already ([withPending]).
 *
 * [task] is the task as the list showed it when the user acted. Its id names
 * it. Without one — a plain line of a plan, or a task typed in and not sent
 * yet — its text on the Daily plan of [date] does: planning that text there
 * gives the id (the server answers with the line that is there already).
 */
@Serializable
data class TaskOp(
    val type: Type,
    val task: Task,
    // The day (YYYY-MM-DD) of the Daily plan the call is about: the plan the
    // task is put on or taken off, and for COMPLETE the day it was done on.
    val date: String,
    // MOVE: the day it goes to.
    val toDate: String? = null,
    // COMPLETE: the note typed in, and the trip it is saved to.
    val note: String? = null,
    val storyId: Long? = null,
    // PLAN_ITEM: the board item to plan.
    val boardId: Long? = null,
    val itemId: String? = null,
) {
    enum class Type {
        /** Put the task on the plan of [date]: one typed in, or one of another plan. */
        PLAN,

        /** Plan a board item for [date]. */
        PLAN_ITEM,

        /** Do a step of the task. */
        COMPLETE,

        /** Take back the step that made it `task.doneCount`. */
        REOPEN,

        /** From the plan of [date] to the plan of [toDate]. */
        MOVE,

        /** Take the task off the plan of [date]. */
        UNPLAN,
    }

    /**
     * Whether this is about [row], a line of the Daily plan of [on] ([on] is
     * null for a list that is no day's: the week's plan, where only an id
     * names a task).
     */
    fun names(row: Task, on: String?): Boolean =
        if (task.id != null && row.id != null) task.id == row.id
        else on != null && on == date && row.text == task.text
}

/**
 * These rows — the Daily plan of [on] as the server last gave it, or with a
 * null [on] the week's plan — as they will be once [ops] have reached the
 * server, oldest first.
 */
fun List<Task>.withPending(ops: List<TaskOp>, on: String?): List<Task> {
    var rows = this
    for (op in ops) {
        fun with() = if (rows.none { op.names(it, on) }) rows + op.task else rows
        fun without() = rows.filterNot { op.names(it, on) }
        fun stepped(by: Int) = rows.map { if (op.names(it, on)) it.stepped(by) else it }

        rows = when (op.type) {
            TaskOp.Type.PLAN, TaskOp.Type.PLAN_ITEM -> if (on == op.date) with() else rows
            TaskOp.Type.COMPLETE -> stepped(1)
            TaskOp.Type.REOPEN -> stepped(-1)
            TaskOp.Type.MOVE -> when (on) {
                op.date -> without()
                op.toDate -> with()
                else -> rows
            }
            TaskOp.Type.UNPLAN -> if (on == op.date) without() else rows
        }
    }
    return rows
}

private val PROGRESS_MARKER = Regex("""\(\d+(?:/\d+)?\)""")

/**
 * The task a step further ([by] = 1) or one back (-1), as the server will
 * describe it: a task without steps is done once, a counted one shows the
 * step it is on, "Do x (2/3)".
 */
internal fun Task.stepped(by: Int): Task {
    if (by > 0 && total == 1 && done) return this
    val count = (doneCount + by).coerceAtLeast(0)
    return copy(
        doneCount = count,
        done = count >= total,
        display = if (total > 1) {
            PROGRESS_MARKER.replaceFirst(text, "(${minOf(count + 1, total)}/$total)")
        } else {
            display
        },
    )
}

/**
 * The task calls a list shows on top of what the server last said: those
 * waiting in the outbox, and those sent since the list was fetched (the
 * server has them; the list in hand doesn't yet). Dropping a call the moment
 * it is sent would show the task as it was before, until the next fetch.
 */
class QueuedTaskOps {

    /** Oldest first. */
    var items: List<OutboxItem> = emptyList()
        private set

    private var sentIds: Set<String> = emptySet()

    /** The ids of the calls sent so far: a list fetched from now on has them. */
    val sent: Set<String> get() = sentIds

    /**
     * Take the task calls of the outbox as they are now. Returns whether any
     * have been sent since the last look, which makes the list worth fetching
     * again.
     */
    fun sync(inOutbox: List<OutboxItem>): Boolean {
        val waiting = inOutbox.map { it.id }.toSet()
        val gone = items.filter { it.id !in waiting }
        val newlySent = gone.any { it.id !in sentIds }
        sentIds = gone.map { it.id }.toSet()
        items = (gone + inOutbox).sortedBy { it.createdAt }
        return newlySent
    }

    /** A list fetched after [covered] were sent is in hand: it has them. */
    fun fetched(covered: Set<String>) {
        items = items.filterNot { it.id in covered }
        sentIds = sentIds - covered
    }

    /** Thrown away without being sent. */
    fun discard(id: String) {
        items = items.filterNot { it.id == id }
    }
}
