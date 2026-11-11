import Foundation
import Testing
@testable import TasksHealth

final class BreadcrumbStoreTests {

    private let dir = FileManager.default.temporaryDirectory.appending(path: UUID().uuidString)
    private let file: URL
    private let store: BreadcrumbStore

    init() {
        file = dir.appending(path: "breadcrumbs.log")
        store = BreadcrumbStore(file: file)
    }

    deinit {
        try? FileManager.default.removeItem(at: dir)
    }

    @Test func appendThenAllRoundTripsAndSortsByTime() {
        store.append(Breadcrumb(t: 300, lat: 3, lng: 3))
        store.append(Breadcrumb(t: 100, lat: 1, lng: 1, acc: 5))
        store.append(Breadcrumb(t: 200, lat: 2, lng: 2))
        let all = store.all()
        #expect(all.map(\.t) == [100, 200, 300])
        #expect(all.first?.acc == 5)
    }

    @Test func allIsEmptyWhenNothingWritten() {
        #expect(store.all().isEmpty)
    }

    @Test func aTornFinalLineIsSkippedNotFatal() throws {
        store.append(Breadcrumb(t: 100, lat: 1, lng: 1))
        let handle = try FileHandle(forWritingTo: file)
        try handle.seekToEnd()
        try handle.write(contentsOf: Data("{not valid json".utf8))
        try handle.close()
        #expect(store.all().count == 1)
    }

    @Test func clearRemovesTheLog() {
        store.append(Breadcrumb(t: 100, lat: 1, lng: 1))
        store.clear()
        #expect(!FileManager.default.fileExists(atPath: file.path))
        #expect(store.all().isEmpty)
    }
}
