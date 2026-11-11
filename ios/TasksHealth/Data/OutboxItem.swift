import Foundation

/// One queued write awaiting delivery to the server: a trip note, a photo, or
/// something done to a task (`task`).
///
/// Everything needed to send is frozen when it is queued, so the entry
/// survives an offline spell or the app being killed: the `comment` already
/// carries the `#poi lat=… lng=…` line (the GPS fix is captured even with no
/// network), `published` is the moment the user acted (not the moment of the
/// upload), and a photo's bytes are copied into the outbox directory
/// (`photoFile`).
///
/// `id` doubles as the server's `idempotency_key`, so a retry whose first
/// answer was lost reuses the existing event instead of making a duplicate.
///
/// `storyId` is nil for a standalone photo (one with no trip): the drainer
/// delivers it through the storyless photo endpoints, and `forStory` never
/// returns it. A task call has no story and no comment of its own: what it
/// does is in `task`.
struct OutboxItem: Codable, Sendable, Equatable, Identifiable {
    enum Kind: String, Codable, Sendable {
        case note = "NOTE"
        case photo = "PHOTO"
        case task = "TASK"
    }

    let id: String
    let kind: Kind
    var storyId: Int64?
    var comment: String
    var published: String
    let createdAt: Int64

    // Photos only:
    var contentType: String?
    var photoFile: String?
    /// Hex SHA-256 of the photo's bytes. Sent to the trip confirm endpoint
    /// so the server dedups the same image within a trip, and used here to
    /// skip queueing a photo that is queued already (see `Outbox`).
    var contentHash: String?
    /// Set together, and only after the bytes are in S3, so a retry after a
    /// failed confirm goes straight to the confirm and never uploads again.
    var presignedKey: String?
    var uploaded = false

    /// Task calls only: what to do, to which task. The drainer writes the
    /// task's id back here once it knows it, so a retry names the same task.
    var task: TaskOp?

    // Delivery bookkeeping, shown in the lists.
    var attempts = 0
    var lastError: String?
    /// A refusal the outbox won't retry by itself (e.g. the trip is
    /// stopped); kept so the user can retry or discard it.
    var failedPermanently = false

    var isPhoto: Bool { kind == .photo }

    var isTask: Bool { kind == .task }
}
