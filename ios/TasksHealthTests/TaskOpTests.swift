import Testing
@testable import TasksHealth

/// What the Today lists show while task calls wait in the outbox.
struct TaskOpTests {

    private let day = "2026-11-11"
    private let tomorrow = "2026-11-12"

    private let bank = PlannedTask(id: "t-bank", text: "call bank")
    private let counted = PlannedTask(
        id: "t-x", text: "Do x (3)", display: "Do x (2/3)", total: 3, doneCount: 1
    )
    private let plain = PlannedTask(text: "written long ago")

    private func op(
        _ type: TaskOp.Kind,
        _ task: PlannedTask,
        date: String? = nil,
        toDate: String? = nil
    ) -> TaskOp {
        TaskOp(type: type, task: task, date: date ?? day, toDate: toDate)
    }

    /// The only row of a list.
    private func single(_ rows: [PlannedTask]) throws -> PlannedTask {
        try #require(rows.count == 1)
        return rows[0]
    }

    @Test func aTaskTypedInShowsOnItsDayOnly() {
        let typed = op(.plan, PlannedTask(text: "buy milk"))

        #expect([bank].withPending([typed], on: day) == [bank, PlannedTask(text: "buy milk")])
        #expect([bank].withPending([typed], on: tomorrow) == [bank])
        // The week's plan is no day's list.
        #expect([bank].withPending([typed], on: nil) == [bank])
    }

    @Test func planningWhatIsOnTheDayAlreadyAddsNothing() {
        let again = [
            op(.plan, bank),
            op(.plan, plain),
            op(.planItem, PlannedTask(text: "call bank")),
        ]

        #expect([bank, plain].withPending(again, on: day) == [bank, plain])
    }

    @Test func aTickShowsAtOnceAndAnUntickAfterIt() throws {
        let tick = op(.complete, bank)
        let ticked = try single([bank].withPending([tick], on: day))

        #expect(ticked.done)
        #expect(ticked.doneCount == 1)

        let untick = op(.reopen, ticked)
        let open = try single([bank].withPending([tick, untick], on: day))

        #expect(!open.done)
        #expect(open.doneCount == 0)
    }

    @Test func aCountedTaskGoesAStepAtATimeAndShowsTheStepItIsOn() throws {
        let step = op(.complete, counted)

        let two = try single([counted].withPending([step], on: day))
        #expect(two.doneCount == 2)
        #expect(!two.done)
        #expect(two.display == "Do x (3/3)")

        let three = try single([counted].withPending([step, step], on: day))
        #expect(three.doneCount == 3)
        #expect(three.done)
        #expect(three.display == "Do x (3/3)")

        // "Add another" goes past the total; "Reset" takes one back.
        let four = try single([counted].withPending([step, step, step], on: day))
        #expect(four.doneCount == 4)
        let back = try single([counted].withPending([step, step, op(.reopen, three)], on: day))
        #expect(back.doneCount == 2)
        #expect(!back.done)
        #expect(back.display == "Do x (3/3)")
    }

    @Test func aTaskWithoutStepsIsDoneOnce() {
        var done = bank
        done.done = true
        done.doneCount = 1

        #expect([done].withPending([op(.complete, done)], on: day) == [done])
    }

    @Test func aTaskTickedOnTheDayIsDoneOnTheWeeksPlanToo() {
        let ticked = [bank, counted].withPending([op(.complete, bank)], on: nil)

        #expect(ticked.map(\.done) == [true, false])
    }

    @Test func aPlainLineIsNamedByItsTextOnItsOwnDay() {
        let tick = op(.complete, plain)

        #expect([plain].withPending([tick], on: day).map(\.done) == [true])
        // The same words on another day's plan are another line.
        #expect([plain].withPending([tick], on: tomorrow).map(\.done) == [false])
        #expect([plain].withPending([tick], on: nil).map(\.done) == [false])
    }

    @Test func aLineThatGotItsIdMeanwhileIsStillTheOneMeant() {
        // The drainer learned the id (the call names it now); the list in
        // hand is from before. And the other way round.
        var withId = plain
        withId.id = "t-new"

        let named = op(.complete, withId)
        #expect([plain].withPending([named], on: day).map(\.done) == [true])

        let byText = op(.complete, plain)
        #expect([withId].withPending([byText], on: day).map(\.done) == [true])
    }

    @Test func aTaskTypedInAndTickedBeforeEitherWasSent() {
        let typed = PlannedTask(text: "buy milk")
        let ops = [op(.plan, typed), op(.complete, typed)]

        #expect([PlannedTask]().withPending(ops, on: day).map(\.done) == [true])
    }

    @Test func movedToTomorrowItLeavesTheDayAndShowsOnTheNext() {
        let move = op(.move, bank, toDate: tomorrow)

        #expect([bank, counted].withPending([move], on: day) == [counted])
        #expect([PlannedTask]().withPending([move], on: tomorrow) == [bank])
        #expect([bank].withPending([move], on: tomorrow) == [bank])
    }

    @Test func removedItIsOffThatDaysList() {
        let remove = op(.unplan, bank)

        #expect([bank, counted].withPending([remove], on: day) == [counted])
        #expect([bank].withPending([remove], on: tomorrow) == [bank])
    }

    // MARK: QueuedTaskOps: which calls a list still has to show

    private func item(_ id: String, _ createdAt: Int64, failed: Bool = false) -> OutboxItem {
        OutboxItem(
            id: id,
            kind: .task,
            storyId: nil,
            comment: "",
            published: "t",
            createdAt: createdAt,
            task: op(.complete, bank),
            failedPermanently: failed
        )
    }

    @Test func aCallThatWasSentIsShownUntilAListFetchedAfterItIsIn() {
        var queue = QueuedTaskOps()
        let a = item("a", 1)
        let b = item("b", 2)

        let nothingSent = queue.sync([a, b])
        #expect(!nothingSent)
        #expect(queue.sent == [])

        // a was sent: worth a fetch, and still shown meanwhile.
        let aSent = queue.sync([b])
        #expect(aSent)
        #expect(queue.items == [a, b])
        let covered = queue.sent
        #expect(covered == ["a"])
        // Nothing new since: no second fetch for the same call.
        let again = queue.sync([b])
        #expect(!again)

        // b is sent while that fetch is on its way: the answer may not have it.
        let bSent = queue.sync([])
        #expect(bSent)
        queue.fetched(covered)

        #expect(queue.items == [b])
        #expect(queue.sent == ["b"])
        let nothingMore = queue.sync([])
        #expect(!nothingMore)
        queue.fetched(queue.sent)
        #expect(queue.items == [])
    }

    @Test func theOutboxSaysHowAWaitingCallIsDoing() {
        var queue = QueuedTaskOps()
        _ = queue.sync([item("a", 1)])

        let sent = queue.sync([item("a", 1, failed: true), item("b", 2)])
        #expect(!sent)

        #expect(queue.items.map(\.failedPermanently) == [true, false])
    }

    @Test func aCallThrownAwayIsNotOneThatWasSent() {
        var queue = QueuedTaskOps()
        _ = queue.sync([item("a", 1, failed: true)])

        queue.discard("a")

        let sent = queue.sync([])
        #expect(!sent)
        #expect(queue.items == [])
    }
}
