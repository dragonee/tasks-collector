import Foundation

/// One thing done to a task on the phone, queued in the `Outbox` until the
/// server has it (see `OutboxDrainer`). Until then the lists show it done
/// already (`withPending`).
///
/// `task` is the task as the list showed it when the user acted. Its id names
/// it. Without one — a plain line of a plan, or a task typed in and not sent
/// yet — its text on the Daily plan of `date` does: planning that text there
/// gives the id (the server answers with the line that is there already).
struct TaskOp: Codable, Sendable, Equatable {
    enum Kind: String, Codable, Sendable {
        /// Put the task on the plan of `date`: one typed in, or one of another plan.
        case plan = "PLAN"
        /// Plan a board item for `date`.
        case planItem = "PLAN_ITEM"
        /// Do a step of the task.
        case complete = "COMPLETE"
        /// Take back the step that made it `task.doneCount`.
        case reopen = "REOPEN"
        /// From the plan of `date` to the plan of `toDate`.
        case move = "MOVE"
        /// Take the task off the plan of `date`.
        case unplan = "UNPLAN"
    }

    var type: Kind
    var task: PlannedTask
    /// The day (YYYY-MM-DD) of the Daily plan the call is about: the plan the
    /// task is put on or taken off, and for a completion the day it was done on.
    var date: String
    /// Move: the day it goes to.
    var toDate: String?
    /// Complete: the note typed in, and the trip it is saved to.
    var note: String?
    var storyId: Int64?
    /// Plan item: the board item to plan.
    var boardId: Int64?
    var itemId: String?

    /// Whether this is about `row`, a line of the Daily plan of `on` (`on`
    /// is nil for a list that is no day's: the week's plan, where only an id
    /// names a task).
    func names(_ row: PlannedTask, on: String?) -> Bool {
        if let mine = task.id, let theirs = row.id { return mine == theirs }
        return on != nil && on == date && row.text == task.text
    }
}

extension [PlannedTask] {
    /// These rows — the Daily plan of `on` as the server last gave it, or
    /// with a nil `on` the week's plan — as they will be once `ops` have
    /// reached the server, oldest first.
    func withPending(_ ops: [TaskOp], on: String?) -> [PlannedTask] {
        var rows = self
        for op in ops {
            func with() -> [PlannedTask] {
                rows.contains { op.names($0, on: on) } ? rows : rows + [op.task]
            }
            func without() -> [PlannedTask] {
                rows.filter { !op.names($0, on: on) }
            }
            func stepped(_ by: Int) -> [PlannedTask] {
                rows.map { op.names($0, on: on) ? $0.stepped(by: by) : $0 }
            }

            switch op.type {
            case .plan, .planItem: rows = on == op.date ? with() : rows
            case .complete: rows = stepped(1)
            case .reopen: rows = stepped(-1)
            case .move:
                if on == op.date {
                    rows = without()
                } else if on != nil, on == op.toDate {
                    rows = with()
                }
            case .unplan: rows = on == op.date ? without() : rows
            }
        }
        return rows
    }
}

extension PlannedTask {
    /// The task a step further (`by` = 1) or one back (-1), as the server
    /// will describe it: a task without steps is done once, a counted one
    /// shows the step it is on, "Do x (2/3)".
    func stepped(by: Int) -> PlannedTask {
        if by > 0, total == 1, done { return self }
        let count = max(doneCount + by, 0)
        var next = self
        next.doneCount = count
        next.done = count >= total
        if total > 1 {
            next.display = text.replacing(
                #/\(\d+(?:/\d+)?\)/#,
                with: "(\(min(count + 1, total))/\(total))",
                maxReplacements: 1
            )
        }
        return next
    }
}

/// The task calls a list shows on top of what the server last said: those
/// waiting in the outbox, and those sent since the list was fetched (the
/// server has them; the list in hand doesn't yet). Dropping a call the moment
/// it is sent would show the task as it was before, until the next fetch.
struct QueuedTaskOps {

    /// Oldest first.
    private(set) var items: [OutboxItem] = []

    /// The ids of the calls sent so far: a list fetched from now on has them.
    private(set) var sent: Set<String> = []

    /// Take the task calls of the outbox as they are now. Returns whether
    /// any have been sent since the last look, which makes the list worth
    /// fetching again.
    mutating func sync(_ inOutbox: [OutboxItem]) -> Bool {
        let waiting = Set(inOutbox.map(\.id))
        let gone = items.filter { !waiting.contains($0.id) }
        let newlySent = gone.contains { !sent.contains($0.id) }
        sent = Set(gone.map(\.id))
        // Stable: calls of the same millisecond keep their order.
        items = (gone + inOutbox).enumerated()
            .sorted { ($0.element.createdAt, $0.offset) < ($1.element.createdAt, $1.offset) }
            .map(\.element)
        return newlySent
    }

    /// A list fetched after `covered` were sent is in hand: it has them.
    mutating func fetched(_ covered: Set<String>) {
        items.removeAll { covered.contains($0.id) }
        sent.subtract(covered)
    }

    /// Thrown away without being sent.
    mutating func discard(_ id: String) {
        items.removeAll { $0.id == id }
    }
}
