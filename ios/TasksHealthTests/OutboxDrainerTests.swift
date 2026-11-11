import Foundation
import Testing
@testable import TasksHealth

final class OutboxDrainerTests {

    private let dir = FileManager.default.temporaryDirectory.appending(path: UUID().uuidString)
    private let outbox: Outbox

    init() {
        outbox = Outbox(dir: dir)
    }

    deinit {
        try? FileManager.default.removeItem(at: dir)
    }

    private let noopPut: OutboxDrainer.PhotoPutter = { _, _, _ in }

    private func enqueuePhoto(storyId: Int64?, bytes: [UInt8]) async throws -> OutboxItem {
        try #require(
            try await outbox.enqueuePhoto(
                storyId: storyId, comment: "cap", published: "t", contentType: "image/jpeg", bytes: Data(bytes)
            )
        )
    }

    @Test func noteSuccessSendsIdempotencyKeyAndReportsSent() async {
        let item = await outbox.enqueueNote(storyId: 5, comment: "hello", published: "2026-06-06T10:00:00Z")
        let api = FakeAPI()
        let outcome = await OutboxDrainer.process(item, api: api, outbox: outbox, put: noopPut)
        #expect(outcome.isSent)
        let notes = await api.noteRequests
        #expect(notes.map(\.idempotencyKey) == [item.id])
        #expect(notes.map(\.storyId) == [5])
    }

    @Test func photoFirstSendPresignsPutsConfirmsAndMarksUploaded() async throws {
        let item = try await enqueuePhoto(storyId: 2, bytes: [1, 2, 3])
        let api = FakeAPI(presignKey: "trips/2/k.jpg", presignUrl: "https://put/x")
        let puts = Puts()
        let outcome = await OutboxDrainer.process(item, api: api, outbox: outbox) { url, _, _ in
            await puts.record(url)
        }
        #expect(outcome.isSent)
        #expect(await puts.urls == ["https://put/x"])
        #expect(await api.presignRequests.count == 1)
        let confirms = await api.confirmRequests
        #expect(confirms.map(\.key) == ["trips/2/k.jpg"])
        #expect(confirms.map(\.idempotencyKey) == [item.id])
        // The item that comes back says it is uploaded.
        #expect(outcome.item.uploaded)
    }

    @Test func photoRetrySkipsReUploadWhenAlreadyUploaded() async throws {
        // As a run before left it: uploaded, and the confirm failed.
        var resumed = try await enqueuePhoto(storyId: 2, bytes: [1, 2, 3])
        resumed.uploaded = true
        resumed.presignedKey = "trips/2/already.jpg"
        await outbox.update(resumed)
        let api = FakeAPI()
        let puts = Puts()
        let outcome = await OutboxDrainer.process(resumed, api: api, outbox: outbox) { url, _, _ in
            await puts.record(url)
        }
        #expect(outcome.isSent)
        #expect(await puts.urls.isEmpty)
        #expect(await api.presignRequests.isEmpty)
        #expect(await api.confirmRequests.map(\.key) == ["trips/2/already.jpg"])
    }

    @Test func standalonePhotoPresignsAndConfirmsViaStorylessEndpoints() async throws {
        // No story: a standalone photo, of no trip.
        let item = try await enqueuePhoto(storyId: nil, bytes: [9])
        let api = FakeAPI(presignKey: "photos/7/k.jpg", presignUrl: "https://put/s")
        let puts = Puts()
        let outcome = await OutboxDrainer.process(item, api: api, outbox: outbox) { url, _, _ in
            await puts.record(url)
        }
        #expect(outcome.isSent)
        #expect(await puts.urls == ["https://put/s"])
        // The trip endpoints are never touched; the storyless ones are.
        #expect(await api.presignRequests.isEmpty)
        #expect(await api.confirmRequests.isEmpty)
        #expect(await api.standalonePresignRequests.count == 1)
        let confirms = await api.standaloneConfirmRequests
        #expect(confirms.map(\.key) == ["photos/7/k.jpg"])
        #expect(confirms.map(\.idempotencyKey) == [item.id])
    }

    @Test func status4xxIsPermanent() async {
        let item = await outbox.enqueueNote(storyId: 1, comment: "x", published: "t")
        let api = FakeAPI(noteError: HTTPError(code: 409))
        let outcome = await OutboxDrainer.process(item, api: api, outbox: outbox, put: noopPut)
        #expect(outcome.isPermanent)
    }

    @Test func status5xxIsRetryable() async {
        let item = await outbox.enqueueNote(storyId: 1, comment: "x", published: "t")
        let api = FakeAPI(noteError: HTTPError(code: 503))
        let outcome = await OutboxDrainer.process(item, api: api, outbox: outbox, put: noopPut)
        #expect(outcome.isRetry)
    }

    @Test func networkErrorIsRetryable() async {
        let item = await outbox.enqueueNote(storyId: 1, comment: "x", published: "t")
        let api = FakeAPI(noteError: URLError(.cannotConnectToHost))
        let outcome = await OutboxDrainer.process(item, api: api, outbox: outbox, put: noopPut)
        #expect(outcome.isRetry)
    }

    @Test func missingPhotoBytesIsPermanentNotAnEndlessRetry() async throws {
        let item = try await enqueuePhoto(storyId: 1, bytes: [7])
        // The bytes are gone and the item is not, as after a corruption.
        try FileManager.default.removeItem(at: try #require(outbox.photoFile(item)))
        let api = FakeAPI()
        let outcome = await OutboxDrainer.process(item, api: api, outbox: outbox, put: noopPut)
        #expect(outcome.isPermanent)
        #expect(await api.presignRequests.isEmpty)
    }

    @Test func aFailedConfirmKeepsWhatTheUploadAchieved() async throws {
        let item = try await enqueuePhoto(storyId: 2, bytes: [1, 2, 3])
        let api = FakeAPI(presignKey: "trips/2/k.jpg", photoError: TransientError(message: "gone"))

        let outcome = await OutboxDrainer.process(item, api: api, outbox: outbox, put: noopPut)

        // The outcome carries the uploaded flag, so the bookkeeping that
        // follows (attempts, last error) doesn't write the item back without it.
        #expect(outcome.isRetry)
        #expect(outcome.item.uploaded)
        #expect(outcome.item.presignedKey == "trips/2/k.jpg")
    }

    // MARK: Task calls

    private let day = "2026-11-11"
    private let bank = PlannedTask(id: "t-bank", text: "call bank")
    private let bankDone = PlannedTask(id: "t-bank", text: "call bank", done: true, doneCount: 1)
    private let plain = PlannedTask(text: "written long ago")

    @discardableResult
    private func queue(
        _ type: TaskOp.Kind,
        _ task: PlannedTask,
        toDate: String? = nil,
        note: String? = nil,
        storyId: Int64? = nil,
        boardId: Int64? = nil,
        itemId: String? = nil
    ) async -> OutboxItem {
        await outbox.enqueueTask(
            TaskOp(
                type: type, task: task, date: day, toDate: toDate,
                note: note, storyId: storyId, boardId: boardId, itemId: itemId
            ),
            published: "2026-11-11T21:30:00+01:00"
        )
    }

    private func send(_ item: OutboxItem, _ api: FakeAPI) async -> OutboxDrainer.Outcome {
        await OutboxDrainer.process(item, api: api, outbox: outbox, put: noopPut)
    }

    @Test func aTickIsSentOnceWhateverIsRetried() async {
        let item = await queue(.complete, bank, note: "sorted", storyId: 4)
        let api = FakeAPI()

        let outcome = await send(item, api)
        #expect(outcome.isSent)

        let expected = FakeAPI.Completion(
            id: "t-bank",
            body: TaskCompleteRequest(
                day: day,
                // The moment of the tap, not of the delivery.
                at: "2026-11-11T21:30:00+01:00",
                note: "sorted",
                storyId: 4,
                idempotencyKey: item.id
            )
        )
        #expect(await api.completions == [expected])
    }

    @Test func anUntickTakesBackTheStepTheUserSaw() async {
        let api = FakeAPI()

        _ = await send(await queue(.reopen, bankDone), api)

        #expect(await api.calls == ["reopen t-bank from 1"])
    }

    @Test func aTypedTaskIsPlannedByItsTextOneWithAnIdByItsId() async {
        let api = FakeAPI()

        _ = await send(await queue(.plan, PlannedTask(text: "buy milk")), api)
        _ = await send(await queue(.plan, bank), api)
        _ = await send(await queue(.planItem, PlannedTask(text: "water plants"), boardId: 12, itemId: "i-1"), api)

        #expect(
            await api.calls == [
                "planText buy milk on \(day)",
                "plan t-bank on \(day)",
                "planItem 12/i-1 on \(day)",
            ]
        )
    }

    @Test func aLineWithoutAnIdGetsOneByBeingPlannedWhereItIs() async {
        let item = await queue(.move, plain, toDate: "2026-11-12")
        let api = FakeAPI()

        let outcome = await send(item, api)

        #expect(outcome.isSent)
        #expect(
            await api.calls == [
                "planText written long ago on \(day)",
                "move id-of-written long ago from \(day) to 2026-11-12",
            ]
        )
    }

    @Test func theIdItGotIsKeptForTheRetry() async throws {
        // Moved, the line is no longer on the plan its text would be looked
        // up on: a retry must name the task it named the first time.
        let item = await queue(.move, plain, toDate: "2026-11-12")
        let api = FakeAPI { $0.hasPrefix("move") ? TransientError(message: "lost") : nil }

        let outcome = await send(item, api)

        #expect(outcome.isRetry)
        #expect(outcome.item.task?.task.id == "id-of-written long ago")
        let kept = await outbox.tasks()
        #expect(kept.map { $0.task?.task.id } == ["id-of-written long ago"])

        let again = FakeAPI()
        let retried = await send(try #require(kept.first), again)
        #expect(retried.isSent)
        #expect(await again.calls == ["move id-of-written long ago from \(day) to 2026-11-12"])
    }

    @Test func removingATaskThatIsGoneAlreadyIsDone() async {
        let gone = FakeAPI(unplanCode: 404)
        let whenGone = await send(await queue(.unplan, bank), gone)
        #expect(whenGone.isSent)
        #expect(await gone.calls == ["unplan t-bank on \(day)"])

        let down = FakeAPI(unplanCode: 503)
        let whenDown = await send(await queue(.unplan, bank), down)
        #expect(whenDown.isRetry)

        let refused = FakeAPI(unplanCode: 400)
        let whenRefused = await send(await queue(.unplan, bank), refused)
        #expect(whenRefused.isPermanent)
    }

    @Test func aRefusedTaskCallIsPermanentAndALostOneIsRetried() async {
        let item = await queue(.complete, bank, storyId: 4)

        // 409: the trip it was saved to is stopped.
        let refused = await send(item, FakeAPI { _ in HTTPError(code: 409) })
        #expect(refused.isPermanent)
        let lost = await send(item, FakeAPI { _ in URLError(.notConnectedToInternet) })
        #expect(lost.isRetry)
    }

    // MARK: A pass over the whole queue

    @Test func taskCallsGoBeforeTripWritesInTheirOwnOrder() async {
        _ = await outbox.enqueueNote(storyId: 5, comment: "a note", published: "t")
        await queue(.complete, bank)
        await queue(.reopen, bankDone)
        let api = FakeAPI()

        let retry = await OutboxDrainer.drain(outbox: outbox, api: api, put: noopPut)

        #expect(!retry)
        #expect(await api.calls == ["complete t-bank", "reopen t-bank from 1", "note a note"])
        #expect(await outbox.all().isEmpty)
    }

    @Test func aTaskCallThatHasToWaitHoldsBackThoseAfterIt() async {
        // Sending the untick alone would leave the task ticked for good once
        // the tick arrives after it.
        _ = await outbox.enqueueNote(storyId: 5, comment: "a note", published: "t")
        await queue(.complete, bank)
        await queue(.reopen, bankDone)
        let api = FakeAPI { $0.hasPrefix("complete") ? HTTPError(code: 503) : nil }

        let retry = await OutboxDrainer.drain(outbox: outbox, api: api, put: noopPut)

        #expect(retry)
        // The trip note is not held back by a task.
        #expect(await api.calls == ["note a note"])
        let left = await outbox.tasks()
        #expect(left.map { $0.task?.type } == [.complete, .reopen])
        #expect(left.map(\.attempts) == [1, 0])
        #expect(left.first?.lastError == "HTTP 503")
    }

    @Test func aRefusedCallIsKeptForTheUserAndTheRestGoesOn() async {
        await queue(.complete, bank, storyId: 4)
        await queue(.plan, PlannedTask(text: "buy milk"))
        let api = FakeAPI { $0.hasPrefix("complete") ? HTTPError(code: 409) : nil }

        let retry = await OutboxDrainer.drain(outbox: outbox, api: api, put: noopPut)
        #expect(!retry)

        let left = await outbox.tasks()
        #expect(left.map(\.failedPermanently) == [true])
        #expect(left.map(\.lastError) == ["HTTP 409"])
        #expect(await api.calls == ["planText buy milk on \(day)"])

        // Not tried again until the user says so.
        let retryAgain = await OutboxDrainer.drain(outbox: outbox, api: api, put: noopPut)
        #expect(!retryAgain)
        #expect(await api.calls.count == 1)
    }
}

/// Stands in for the server. Task calls and trip notes are logged in `calls`,
/// one line each; `failing` may refuse a call by that line.
private actor FakeAPI: OutboxAPI {

    struct Completion: Equatable {
        let id: String
        let body: TaskCompleteRequest
    }

    private let presignKey: String
    private let presignUrl: String
    private let noteError: (any Error)?
    private let photoError: (any Error)?
    private let unplanCode: Int
    private let failing: @Sendable (String) -> (any Error)?

    private(set) var calls: [String] = []
    private(set) var completions: [Completion] = []
    private(set) var noteRequests: [TripNoteRequest] = []
    private(set) var presignRequests: [PhotoPresignRequest] = []
    private(set) var confirmRequests: [PhotoConfirmRequest] = []
    private(set) var standalonePresignRequests: [StandalonePhotoPresignRequest] = []
    private(set) var standaloneConfirmRequests: [StandalonePhotoConfirmRequest] = []

    init(
        presignKey: String = "k",
        presignUrl: String = "https://put/url",
        noteError: (any Error)? = nil,
        photoError: (any Error)? = nil,
        unplanCode: Int = 204,
        failing: @escaping @Sendable (String) -> (any Error)? = { _ in nil }
    ) {
        self.presignKey = presignKey
        self.presignUrl = presignUrl
        self.noteError = noteError
        self.photoError = photoError
        self.unplanCode = unplanCode
        self.failing = failing
    }

    private func call(_ line: String) throws {
        if let error = failing(line) { throw error }
        calls.append(line)
    }

    func addTripNote(_ body: TripNoteRequest) async throws {
        if let noteError { throw noteError }
        try call("note \(body.comment)")
        noteRequests.append(body)
    }

    func presignPhoto(_ body: PhotoPresignRequest) async throws -> PhotoPresignResponse {
        presignRequests.append(body)
        return PhotoPresignResponse(key: presignKey, uploadUrl: presignUrl)
    }

    func addTripPhoto(_ body: PhotoConfirmRequest) async throws {
        if let photoError { throw photoError }
        confirmRequests.append(body)
    }

    func presignStandalonePhoto(_ body: StandalonePhotoPresignRequest) async throws -> PhotoPresignResponse {
        standalonePresignRequests.append(body)
        return PhotoPresignResponse(key: presignKey, uploadUrl: presignUrl)
    }

    func addStandalonePhoto(_ body: StandalonePhotoConfirmRequest) async throws {
        if let photoError { throw photoError }
        standaloneConfirmRequests.append(body)
    }

    func planText(_ body: PlanTextRequest) async throws -> PlannedTask {
        try call("planText \(body.text) on \(body.date)")
        return PlannedTask(id: "id-of-\(body.text)", text: body.text)
    }

    func planItem(_ body: PlanItemRequest) async throws -> PlannedTask {
        try call("planItem \(body.boardId)/\(body.itemId) on \(body.date)")
        return PlannedTask(id: "id-of-\(body.itemId)", text: "")
    }

    func planTask(id: String, _ body: PlanRef) async throws -> PlannedTask {
        try call("plan \(id) on \(body.date)")
        return PlannedTask(id: id, text: "")
    }

    func unplanTask(id: String, _ body: PlanRef) async throws {
        try call("unplan \(id) on \(body.date)")
        if !(200..<300).contains(unplanCode) { throw HTTPError(code: unplanCode) }
    }

    func moveTask(id: String, _ body: TaskMoveRequest) async throws -> PlannedTask {
        try call("move \(id) from \(body.fromDate) to \(body.toDate)")
        return PlannedTask(id: id, text: "")
    }

    func completeTask(id: String, _ body: TaskCompleteRequest) async throws -> PlannedTask {
        try call("complete \(id)")
        completions.append(Completion(id: id, body: body))
        return PlannedTask(id: id, text: "")
    }

    func reopenTask(id: String, _ body: TaskReopenRequest) async throws -> PlannedTask {
        try call("reopen \(id) from \(body.doneCount.map(String.init) ?? "nil")")
        return PlannedTask(id: id, text: "")
    }
}

/// The uploads a test's stand-in for S3 was asked for.
private actor Puts {
    private(set) var urls: [String] = []

    func record(_ url: String) {
        urls.append(url)
    }
}

private extension OutboxDrainer.Outcome {
    var item: OutboxItem {
        switch self {
        case .sent(let item), .retry(let item, _), .permanent(let item, _): item
        }
    }

    var isSent: Bool {
        if case .sent = self { true } else { false }
    }

    var isRetry: Bool {
        if case .retry = self { true } else { false }
    }

    var isPermanent: Bool {
        if case .permanent = self { true } else { false }
    }
}
