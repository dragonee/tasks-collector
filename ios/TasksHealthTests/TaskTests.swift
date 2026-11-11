import Foundation
import Testing
@testable import TasksHealth

struct TaskTests {

    private func task(_ id: String?, _ text: String, done: Bool = false) -> PlannedTask {
        PlannedTask(id: id, text: text, done: done)
    }

    /// As `TasksClient` encodes a request, with the keys in a known order.
    private func json(_ body: some Encodable) throws -> String {
        let encoder = JSONEncoder()
        encoder.outputFormatting = .sortedKeys
        return String(decoding: try encoder.encode(body), as: UTF8.self)
    }

    @Test func anAgendaAsTheServerSendsIt() throws {
        let agenda = try JSONDecoder().decode(
            AgendaResponse.self,
            from: Data(
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
                """.utf8
            )
        )

        #expect(agenda.daily.tasks.count == 1)
        let counted = try #require(agenda.daily.tasks.first)
        #expect(counted.id == "7b1e")
        #expect(counted.shown == "Do x (2/3)")
        #expect(counted.total == 3)
        #expect(counted.doneCount == 1)
        #expect(!counted.isCountedAndDone)

        #expect(agenda.weekly.tasks.count == 1)
        let plain = try #require(agenda.weekly.tasks.first)
        #expect(plain.id == nil)
        #expect(plain.key == "text:a plain line")
        #expect(plain.mark == "~")
        #expect(agenda.monthly.tasks.isEmpty)
    }

    @Test func aRowIsToldFromTheOthersByItsTask() {
        // Two tasks may read the same; a plain line has only its text.
        #expect(task("a", "same").key == "a")
        #expect(task("b", "same").key == "b")
        #expect(task(nil, "same").key == "text:same")
    }

    @Test func onlyACountedTaskWithAllItsStepsDoneOffersAnother() {
        #expect(PlannedTask(text: "Do x (3)", total: 3, doneCount: 3).isCountedAndDone)
        #expect(PlannedTask(text: "Do x (3)", total: 3, doneCount: 4).isCountedAndDone)
        #expect(!PlannedTask(text: "Do x (3)", total: 3, doneCount: 2).isCountedAndDone)
        #expect(!PlannedTask(text: "plain", total: 1, doneCount: 1).isCountedAndDone)
    }

    @Test func aTaskOfTheWeekDoneOnAnotherDayIsNotOfferedAgain() {
        let week = [
            task("done-yesterday", "write report", done: true),
            task("on-today", "call bank"),
            task("left", "read a book"),
            task(nil, "an old plain line"),
        ]
        let today = [task("on-today", "call bank"), task("other", "buy bread")]

        #expect(weekPlanLeft(week, today: today).map(\.text) == ["read a book", "an old plain line"])
    }

    @Test func aRequestToPlanWhatWasTypedNamesNoBoardItem() throws {
        // The server wants either text or an item; nulls would be sent too.
        #expect(
            try json(PlanTextRequest(text: "call bank", date: "2026-11-11"))
                == #"{"date":"2026-11-11","text":"call bank","thread":"Daily"}"#
        )
        #expect(
            try json(PlanItemRequest(boardId: 12, itemId: "i-1", date: "2026-11-11"))
                == #"{"board_id":12,"date":"2026-11-11","item_id":"i-1","thread":"Daily"}"#
        )
    }
}
