import CryptoKit
import Foundation

/// Durable, file-backed queue of writes: trip notes and photos, and what is
/// done to tasks (see `OutboxItem`).
///
/// Each item is one JSON file in `dir`; a photo's bytes live in a file next
/// to it. Filenames start with a zero-padded `createdAt`, so sorting the
/// directory by name gives delivery order, oldest first. The directory is the
/// only source of truth — there is no index in memory — so it survives the
/// process dying and is read fresh on every drain.
///
/// An actor: the queue is read and written one call at a time, off the main
/// thread.
actor Outbox {

    private let dir: URL
    private let files = FileManager.default

    init(dir: URL) {
        self.dir = dir
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
    }

    func enqueueNote(storyId: Int64, comment: String, published: String) -> OutboxItem {
        let item = OutboxItem(
            id: Self.newId(),
            kind: .note,
            storyId: storyId,
            comment: comment,
            published: published,
            createdAt: Date().epochMillis
        )
        write(item)
        return item
    }

    /// Queue a photo. Returns nil (and writes nothing) when the same image
    /// is queued for this scope already: the content hash dedups a quick
    /// double pick or an overlapping selection before anything is uploaded.
    /// A copy that failed for good is not counted, so picking it again gives
    /// it a fresh try.
    func enqueuePhoto(
        storyId: Int64?,
        comment: String,
        published: String,
        contentType: String,
        bytes: Data
    ) throws -> OutboxItem? {
        let contentHash = Self.sha256Hex(bytes)
        let scope = storyId.map(forStory) ?? standalone()
        if scope.contains(where: { $0.isPhoto && !$0.failedPermanently && $0.contentHash == contentHash }) {
            return nil
        }
        let id = Self.newId()
        let createdAt = Date().epochMillis
        let photoName = Self.baseName(createdAt, id) + "." + Self.ext(for: contentType)
        try bytes.write(to: dir.appending(path: photoName), options: .atomic)
        let item = OutboxItem(
            id: id,
            kind: .photo,
            storyId: storyId,
            comment: comment,
            published: published,
            createdAt: createdAt,
            contentType: contentType,
            photoFile: photoName,
            contentHash: contentHash
        )
        write(item)
        return item
    }

    /// Queue something done to a task. `published` is the moment of the tap.
    /// Task calls build on each other (tick, then untick), so each is filed
    /// after everything queued before it, even within the same millisecond.
    @discardableResult
    func enqueueTask(_ op: TaskOp, published: String) -> OutboxItem {
        let item = OutboxItem(
            id: Self.newId(),
            kind: .task,
            storyId: nil,
            comment: "",
            published: published,
            createdAt: max(Date().epochMillis, lastCreatedAt() + 1),
            task: op
        )
        write(item)
        return item
    }

    /// All queued items, oldest first.
    func all() -> [OutboxItem] {
        names()
            .filter { $0.hasSuffix(".json") }
            .sorted()
            .compactMap(read)
    }

    func forStory(_ storyId: Int64) -> [OutboxItem] {
        all().filter { $0.storyId == storyId }
    }

    /// Standalone (storyless) photos, oldest first.
    func standalone() -> [OutboxItem] {
        all().filter { $0.isPhoto && $0.storyId == nil }
    }

    /// Task calls, oldest first.
    func tasks() -> [OutboxItem] {
        all().filter(\.isTask)
    }

    /// Write a changed item back to its file (the name is the same: `id`
    /// and `createdAt` don't change).
    func update(_ item: OutboxItem) {
        write(item)
    }

    /// Remove an item's JSON and its photo file, if any.
    func remove(_ item: OutboxItem) {
        try? files.removeItem(at: dir.appending(path: Self.jsonName(item)))
        if let photo = photoFile(item) { try? files.removeItem(at: photo) }
    }

    /// Where a photo's bytes are.
    nonisolated func photoFile(_ item: OutboxItem) -> URL? {
        item.photoFile.map { dir.appending(path: $0) }
    }

    func photoBytes(_ item: OutboxItem) -> Data? {
        photoFile(item).flatMap { try? Data(contentsOf: $0) }
    }

    private func write(_ item: OutboxItem) {
        guard let data = try? JSONEncoder().encode(item) else { return }
        // Atomic, so a crash mid-write never leaves half an item.
        try? data.write(to: dir.appending(path: Self.jsonName(item)), options: .atomic)
    }

    private func read(_ name: String) -> OutboxItem? {
        guard let data = try? Data(contentsOf: dir.appending(path: name)) else { return nil }
        return try? JSONDecoder().decode(OutboxItem.self, from: data)
    }

    private func names() -> [String] {
        (try? files.contentsOfDirectory(atPath: dir.path)) ?? []
    }

    /// The `createdAt` of the newest file in the queue (0 when it is empty).
    private func lastCreatedAt() -> Int64 {
        names().compactMap { Int64($0.prefix(16)) }.max() ?? 0
    }

    private static func newId() -> String {
        UUID().uuidString.lowercased()
    }

    private static func jsonName(_ item: OutboxItem) -> String {
        baseName(item.createdAt, item.id) + ".json"
    }

    private static func baseName(_ createdAt: Int64, _ id: String) -> String {
        String(format: "%016lld-%@", createdAt, String(id.prefix(8)))
    }

    static func sha256Hex(_ bytes: Data) -> String {
        SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined()
    }

    private static func ext(for contentType: String) -> String {
        switch contentType.lowercased() {
        case "image/jpeg", "image/jpg": "jpg"
        case "image/png": "png"
        case "image/webp": "webp"
        case "image/heic", "image/heif": "heic"
        default: "img"
        }
    }
}
