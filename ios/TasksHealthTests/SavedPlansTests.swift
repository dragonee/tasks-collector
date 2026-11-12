import Foundation
import Testing
@testable import TasksHealth

final class SavedPlansTests {

    private let dir = FileManager.default.temporaryDirectory.appending(path: UUID().uuidString)
    private let plans: SavedPlans

    private let today = Day(year: 2026, month: 11, day: 12)
    private let account = SavedPlans.account(serverUrl: "https://tasks", apiToken: "token")

    init() {
        plans = SavedPlans(dir: dir)
    }

    deinit {
        try? FileManager.default.removeItem(at: dir)
    }

    private func agenda(_ texts: String...) -> AgendaResponse {
        var agenda = AgendaResponse()
        agenda.daily.tasks = texts.enumerated().map { i, text in
            PlannedTask(id: "t\(i)", text: text, done: i == 0)
        }
        return agenda
    }

    @Test func thePlansOfADayComeBackAsTheyWereFetched() async throws {
        let at = Date(timeIntervalSince1970: 1_700_000_000)
        await plans.save(
            account: account, day: "2026-11-12",
            agenda: agenda("Call the client", "Write the report"), savedAt: at, today: today
        )

        let saved = try #require(await plans.load(account: account, day: "2026-11-12"))

        #expect(saved.agenda == agenda("Call the client", "Write the report"))
        #expect(saved.savedAt == at)
    }

    @Test func aDaySavedAgainIsTheLaterFetch() async {
        await plans.save(account: account, day: "2026-11-12", agenda: agenda("Before"), today: today)
        await plans.save(account: account, day: "2026-11-12", agenda: agenda("After"), today: today)

        #expect(await plans.load(account: account, day: "2026-11-12")?.agenda == agenda("After"))
    }

    @Test func aDayNeverFetchedHasNothing() async {
        #expect(await plans.load(account: account, day: "2026-11-13") == nil)
    }

    @Test func anotherAccountSeesNothingOfWhatThisOneFetched() async {
        await plans.save(account: account, day: "2026-11-12", agenda: agenda("Mine"), today: today)

        let otherToken = SavedPlans.account(serverUrl: "https://tasks", apiToken: "another token")
        let otherServer = SavedPlans.account(serverUrl: "https://elsewhere", apiToken: "token")
        #expect(await plans.load(account: otherToken, day: "2026-11-12") == nil)
        #expect(await plans.load(account: otherServer, day: "2026-11-12") == nil)
    }

    @Test func daysMoreThanTwoWeeksAwayAreThrownAway() async {
        await plans.save(
            account: account, day: "2026-10-01", agenda: agenda("Long ago"),
            today: today.adding(days: -42)
        )
        await plans.save(
            account: account, day: "2026-10-29", agenda: agenda("Two weeks ago"),
            today: today.adding(days: -14)
        )

        await plans.save(account: account, day: "2026-11-12", agenda: agenda("Today"), today: today)

        #expect(await plans.load(account: account, day: "2026-10-01") == nil)
        #expect(await plans.load(account: account, day: "2026-10-29")?.agenda == agenda("Two weeks ago"))
    }

    @Test func aBrokenFileIsNothingSaved() async throws {
        try Data("{not json".utf8).write(to: dir.appending(path: "2026-11-12.json"))

        #expect(await plans.load(account: account, day: "2026-11-12") == nil)
    }

    @Test func theAccountIsAHashNotTheToken() {
        #expect(account.count == 64)
        #expect(!account.contains("token"))
    }
}
