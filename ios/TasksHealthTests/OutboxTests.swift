import Foundation
import Testing
@testable import TasksHealth

final class OutboxTests {

    private let dir = FileManager.default.temporaryDirectory.appending(path: UUID().uuidString)
    private let outbox: Outbox

    init() {
        outbox = Outbox(dir: dir)
    }

    deinit {
        try? FileManager.default.removeItem(at: dir)
    }

    @Test func enqueueNotePersistsARetrievableItem() async {
        let item = await outbox.enqueueNote(
            storyId: 7, comment: "#poi lat=1.0 lng=2.0\nhi", published: "2026-06-06T10:00:00Z"
        )
        let all = await outbox.all()
        #expect(all.count == 1)
        #expect(all.first?.id == item.id)
        #expect(all.first?.kind == .note)
        #expect(all.first?.storyId == 7)
        #expect(all.first?.comment == "#poi lat=1.0 lng=2.0\nhi")
    }

    @Test func enqueuePhotoWritesThePhotoBytesAlongsideTheItem() async throws {
        let bytes = Data([1, 2, 3, 4, 5])
        let item = try #require(
            try await outbox.enqueuePhoto(
                storyId: 3, comment: "caption", published: "2026-06-06T10:00:00Z",
                contentType: "image/jpeg", bytes: bytes
            )
        )
        #expect(item.isPhoto)
        #expect(item.contentType == "image/jpeg")
        #expect(outbox.photoFile(item)?.lastPathComponent.hasSuffix(".jpg") == true)
        #expect(await outbox.photoBytes(item) == bytes)
    }

    @Test func allReturnsItemsOldestFirst() async throws {
        // createdAt starts the file name; a pause makes the two differ.
        let a = await outbox.enqueueNote(storyId: 1, comment: "first", published: "t1")
        try await Task.sleep(for: .milliseconds(2))
        let b = await outbox.enqueueNote(storyId: 1, comment: "second", published: "t2")
        #expect(await outbox.all().map(\.id) == [a.id, b.id])
    }

    @Test func forStoryFiltersByStory() async {
        _ = await outbox.enqueueNote(storyId: 1, comment: "a", published: "t")
        _ = await outbox.enqueueNote(storyId: 2, comment: "b", published: "t")
        #expect(await outbox.forStory(1).count == 1)
        #expect(await outbox.forStory(2).map(\.storyId) == [2])
    }

    @Test func enqueuePhotoWithNilStoryIsAStandalonePhoto() async throws {
        let bytes = Data([4, 2])
        let item = try #require(
            try await outbox.enqueuePhoto(
                storyId: nil, comment: "cap", published: "2026-06-06T10:00:00Z",
                contentType: "image/jpeg", bytes: bytes
            )
        )
        #expect(item.storyId == nil)
        let all = await outbox.all()
        #expect(all.count == 1)
        let reloaded = try #require(all.first)
        #expect(reloaded.storyId == nil)
        #expect(await outbox.photoBytes(reloaded) == bytes)
        // A storyless photo never shows under any trip, but is still drained.
        #expect(await outbox.forStory(0).isEmpty)
        #expect(await outbox.all().count == 1)
    }

    @Test func standaloneReturnsOnlyStorylessItems() async throws {
        _ = await outbox.enqueueNote(storyId: 1, comment: "trip note", published: "t")
        _ = try await outbox.enqueuePhoto(
            storyId: 1, comment: "trip photo", published: "t", contentType: "image/jpeg", bytes: Data([1])
        )
        let solo = try #require(
            try await outbox.enqueuePhoto(
                storyId: nil, comment: "standalone", published: "t", contentType: "image/jpeg", bytes: Data([2])
            )
        )
        #expect(await outbox.standalone().map(\.id) == [solo.id])
    }

    @Test func taskCallsAreKeptInTheOrderTheyWereMade() async {
        // Queued within the same millisecond more often than not; a random
        // id must not decide which comes first.
        let texts = (1...20).map { "task \($0)" }
        for text in texts {
            await outbox.enqueueTask(
                TaskOp(type: .plan, task: PlannedTask(text: text), date: "2026-11-11"), published: "t"
            )
        }

        #expect(await outbox.tasks().map { $0.task?.task.text } == texts)
        #expect(await outbox.all().map { $0.task?.task.text } == texts)
    }

    @Test func aTaskCallIsItsOwnKindOfItem() async throws {
        _ = await outbox.enqueueNote(storyId: 1, comment: "trip note", published: "t")
        let solo = try #require(
            try await outbox.enqueuePhoto(
                storyId: nil, comment: "standalone", published: "t", contentType: "image/jpeg", bytes: Data([2])
            )
        )
        let call = await outbox.enqueueTask(
            TaskOp(
                type: .complete,
                task: PlannedTask(id: "t-1", text: "call bank"),
                date: "2026-11-11",
                note: "sorted",
                storyId: 4
            ),
            published: "2026-11-11T10:00:00+01:00"
        )

        let tasks = await outbox.tasks()
        #expect(tasks == [call])
        let read = try #require(tasks.first)
        #expect(read.kind == .task)
        #expect(read.task?.note == "sorted")
        // Saved to a trip or not, it is no trip write and no standalone photo.
        #expect(read.storyId == nil)
        #expect(await outbox.forStory(4).isEmpty)
        #expect(await outbox.standalone().map(\.id) == [solo.id])
    }

    @Test func updateRewritesTheSameFileInPlace() async throws {
        let item = await outbox.enqueueNote(storyId: 1, comment: "x", published: "t")
        var changed = item
        changed.attempts = 3
        changed.lastError = "boom"
        await outbox.update(changed)
        let all = await outbox.all()
        // No second file.
        #expect(all.count == 1)
        let reloaded = try #require(all.first)
        #expect(reloaded.id == item.id)
        #expect(reloaded.attempts == 3)
        #expect(reloaded.lastError == "boom")
    }

    @Test func removeDeletesTheJsonAndThePhotoFile() async throws {
        let item = try #require(
            try await outbox.enqueuePhoto(
                storyId: 1, comment: "c", published: "t", contentType: "image/png", bytes: Data([9])
            )
        )
        let photo = try #require(outbox.photoFile(item))
        #expect(FileManager.default.fileExists(atPath: photo.path))
        await outbox.remove(item)
        #expect(await outbox.all().isEmpty)
        #expect(!FileManager.default.fileExists(atPath: photo.path))
    }

    @Test func photoBytesIsNilForANote() async {
        let item = await outbox.enqueueNote(storyId: 1, comment: "x", published: "t")
        #expect(await outbox.photoBytes(item) == nil)
    }

    @Test func enqueuePhotoSkipsAnIdenticalImageAlreadyQueuedForTheStory() async throws {
        let bytes = Data([1, 2, 3])
        let first = try await outbox.enqueuePhoto(
            storyId: 1, comment: "a", published: "t1", contentType: "image/jpeg", bytes: bytes
        )
        // The same bytes have the same hash: nothing is queued.
        let second = try await outbox.enqueuePhoto(
            storyId: 1, comment: "b", published: "t2", contentType: "image/jpeg", bytes: bytes
        )
        #expect(first != nil)
        #expect(second == nil)
        #expect(await outbox.forStory(1).count == 1)
    }

    @Test func enqueuePhotoDedupsPerScopeNotAcrossStories() async throws {
        let bytes = Data([7, 8, 9])
        let one = try await outbox.enqueuePhoto(
            storyId: 1, comment: "a", published: "t", contentType: "image/jpeg", bytes: bytes
        )
        // The same image on another trip is allowed.
        let other = try await outbox.enqueuePhoto(
            storyId: 2, comment: "a", published: "t", contentType: "image/jpeg", bytes: bytes
        )
        #expect(one != nil)
        #expect(other != nil)
        #expect(await outbox.forStory(1).count == 1)
        #expect(await outbox.forStory(2).count == 1)
    }

    @Test func enqueuePhotoReEnqueuesAnImageWhosePriorCopyFailedPermanently() async throws {
        let bytes = Data([5, 5, 5])
        var first = try #require(
            try await outbox.enqueuePhoto(
                storyId: 1, comment: "a", published: "t", contentType: "image/jpeg", bytes: bytes
            )
        )
        first.failedPermanently = true
        await outbox.update(first)
        // A copy that failed for good must not block a fresh attempt.
        let retry = try await outbox.enqueuePhoto(
            storyId: 1, comment: "a", published: "t", contentType: "image/jpeg", bytes: bytes
        )
        #expect(retry != nil)
    }
}
