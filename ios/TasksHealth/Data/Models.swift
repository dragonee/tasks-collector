import Foundation

// What the server sends and takes. The keys are the server's (snake_case);
// a key the server leaves out takes the default written in `init(from:)`,
// and one it adds is ignored.

extension KeyedDecodingContainer {
    /// The value at `key`, or `fallback` when the key is missing or null.
    func value<T: Decodable>(_ key: Key, or fallback: T) throws -> T {
        try decodeIfPresent(T.self, forKey: key) ?? fallback
    }
}

// MARK: - Habits and health

struct TrackHabitRequest: Encodable, Sendable {
    let keyword: String
    let date: String
    let note: String
}

struct TrackHabitTextRequest: Encodable, Sendable {
    /// One line starting with '#' or '!'. The server makes one HabitTracked
    /// per hashtag in it, so a habit can be tracked several times a day
    /// (unlike the idempotent api/v1/habit/track/).
    let text: String
    /// When it happened, so the entry lands on that day.
    let published: String
}

/// One option of the "track a habit" picker (habit/keywords/mine/).
struct HabitKeyword: Decodable, Sendable, Identifiable, Equatable {
    let id: Int64
    let keyword: String
}

/// Server-derived health data: the body weight last recorded, and when.
struct HealthDataResponse: Decodable, Sendable, Equatable {
    var weightKg: Double?
    var recordedAt: String?

    enum CodingKeys: String, CodingKey {
        case weightKg = "weight_kg"
        case recordedAt = "recorded_at"
    }
}

// MARK: - Tasks

/// A task as the server describes it (api/v1/tasks/): one of a day's lines,
/// or of the week's plan. (`Task` is Swift's own word, hence the name.)
struct PlannedTask: Codable, Sendable, Equatable {
    /// Nil for a plain line of a plan: one nothing was done with as a task
    /// yet. Planning its text makes it a task and gives it an id.
    var id: String?
    /// As written, e.g. "Do x (3)".
    var text: String
    /// As lists show it: a counted task with the step it is on, "Do x (2/3)".
    var display: String = ""
    var done: Bool = false
    /// "~" (better) / "^" (best) for a task done with that mark.
    var mark: String?
    /// Steps: one for a plain task; a counted one is done at
    /// `doneCount >= total` and may go past it ("add another").
    var total: Int = 1
    var doneCount: Int = 0

    enum CodingKeys: String, CodingKey {
        case id, text, display, done, mark, total
        case doneCount = "done_count"
    }

    init(
        id: String? = nil,
        text: String,
        display: String = "",
        done: Bool = false,
        mark: String? = nil,
        total: Int = 1,
        doneCount: Int = 0
    ) {
        self.id = id
        self.text = text
        self.display = display
        self.done = done
        self.mark = mark
        self.total = total
        self.doneCount = doneCount
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decodeIfPresent(String.self, forKey: .id)
        text = try c.decode(String.self, forKey: .text)
        display = try c.value(.display, or: "")
        done = try c.value(.done, or: false)
        mark = try c.decodeIfPresent(String.self, forKey: .mark)
        total = try c.value(.total, or: 1)
        doneCount = try c.value(.doneCount, or: 0)
    }

    /// What a row shows.
    var shown: String { display.isEmpty ? text : display }

    /// What tells this row from the others: its task, or its text while it
    /// is a plain line.
    var key: String { id ?? "text:\(text)" }

    /// A counted task that is done: tapping it offers another step or taking
    /// the last one back, instead of unticking straight away.
    var isCountedAndDone: Bool { total > 1 && doneCount >= total }
}

/// What is left of the week's plan to offer on a day: the tasks that are not
/// done (wherever they were ticked) and not on that day's list already.
func weekPlanLeft(_ weekPlan: [PlannedTask], today: [PlannedTask]) -> [PlannedTask] {
    let onTheDay = Set(today.map(\.key))
    return weekPlan.filter { !$0.done && !onTheDay.contains($0.key) }
}

struct AgendaPlan: Codable, Sendable, Equatable {
    var tasks: [PlannedTask] = []

    enum CodingKeys: String, CodingKey { case tasks }

    init() {}

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        tasks = try c.value(.tasks, or: [])
    }
}

/// GET api/v1/tasks/agenda/?date= — the plan of that day, of its week and of
/// its month. Done is the task's: a task of the week ticked on another day
/// comes back done here.
struct AgendaResponse: Codable, Sendable, Equatable {
    var daily = AgendaPlan()
    var weekly = AgendaPlan()
    var monthly = AgendaPlan()

    enum CodingKeys: String, CodingKey { case daily, weekly, monthly }

    init() {}

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        daily = try c.value(.daily, or: AgendaPlan())
        weekly = try c.value(.weekly, or: AgendaPlan())
        monthly = try c.value(.monthly, or: AgendaPlan())
    }
}

/// POST api/v1/tasks/ — plan something typed on the plan of `thread` that the
/// day `date` falls in. The server answers with the task of that text if the
/// user has one planned already (a line of the week pulled into a day), else
/// a new one.
struct PlanTextRequest: Encodable, Sendable, Equatable {
    let text: String
    let date: String
    var thread = "Daily"
}

/// POST api/v1/tasks/ — plan a board item (an unscheduled task becomes a task).
struct PlanItemRequest: Encodable, Sendable, Equatable {
    let boardId: Int64
    let itemId: String
    let date: String
    var thread = "Daily"

    enum CodingKeys: String, CodingKey {
        case boardId = "board_id"
        case itemId = "item_id"
        case date, thread
    }
}

/// One of the user's plans: the one of `thread` that the day `date` falls in.
struct PlanRef: Encodable, Sendable, Equatable {
    let date: String
    var thread = "Daily"
}

struct TaskMoveRequest: Encodable, Sendable, Equatable {
    let fromDate: String
    let toDate: String
    var thread = "Daily"

    enum CodingKeys: String, CodingKey {
        case fromDate = "from_date"
        case toDate = "to_date"
        case thread
    }
}

struct TaskCompleteRequest: Encodable, Sendable, Equatable {
    /// The day it was done on for the user (YYYY-MM-DD): the reflection it
    /// lands in.
    let day: String
    /// The moment of the tap, which is also the published time of the
    /// journal entry a note makes.
    let at: String
    /// A journal note. Nil or empty: no journal entry, unless it is saved to
    /// a trip.
    var note: String?
    /// "Save to trip": link the journal entry to this active trip.
    var storyId: Int64?
    /// Sent again unchanged on a retry: the server completes once per key.
    let idempotencyKey: String

    enum CodingKeys: String, CodingKey {
        case day, at, note
        case storyId = "story_id"
        case idempotencyKey = "idempotency_key"
    }
}

struct TaskReopenRequest: Encodable, Sendable, Equatable {
    /// How many steps the task had done when the user took one back. The
    /// server takes a step back only while it still has that many, so the
    /// request sent again takes back nothing more. Nil: the last step,
    /// whatever the count.
    var doneCount: Int?

    enum CodingKeys: String, CodingKey { case doneCount = "done_count" }
}

// MARK: - Board

struct BoardItem: Decodable, Sendable, Equatable {
    /// The item's id and its board: what `PlanItemRequest` names it by.
    var id: String?
    var boardId: Int64 = 0
    var text: String
    /// "must" | "should" | "could" | "wont", or nil when unclassified.
    var moscow: String?
    /// Nesting level in the board tree (0 = root).
    var depth: Int = 0
    var done: Bool = false

    enum CodingKeys: String, CodingKey {
        case id, text, moscow, depth, done
        case boardId = "board_id"
    }

    init(id: String? = nil, boardId: Int64 = 0, text: String, moscow: String? = nil, depth: Int = 0, done: Bool = false) {
        self.id = id
        self.boardId = boardId
        self.text = text
        self.moscow = moscow
        self.depth = depth
        self.done = done
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decodeIfPresent(String.self, forKey: .id)
        boardId = try c.value(.boardId, or: 0)
        text = try c.decode(String.self, forKey: .text)
        moscow = try c.decodeIfPresent(String.self, forKey: .moscow)
        depth = try c.value(.depth, or: 0)
        done = try c.value(.done, or: false)
    }
}

struct BoardItemsResponse: Decodable, Sendable {
    var items: [BoardItem] = []

    enum CodingKeys: String, CodingKey { case items }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        items = try c.value(.items, or: [])
    }
}

/// Append a free-typed unscheduled task to the caller's current board. The
/// thread is left out: the server defaults it to the user's board, the same
/// one board/items/ returns.
struct UnscheduledTaskRequest: Encodable, Sendable {
    let text: String
}

// MARK: - Trips

struct TripSummary: Decodable, Sendable, Equatable, Identifiable {
    let id: Int64
    let type: String
    let title: String
    let started: String
    var stopped: String?
}

struct TripStartRequest: Encodable, Sendable {
    var title: String?
    var type = "trip"
}

struct TripStoryIdRequest: Encodable, Sendable {
    let storyId: Int64

    enum CodingKeys: String, CodingKey { case storyId = "story_id" }
}

struct TripStopRequest: Encodable, Sendable {
    let storyId: Int64
    /// When the trip actually ended — the "I got home yesterday and forgot
    /// to stop it" case. Nil stops it now. The server clamps a future value
    /// to its own now and rejects anything before the trip started.
    var stopped: String?

    enum CodingKeys: String, CodingKey {
        case storyId = "story_id"
        case stopped
    }
}

struct TripUpdateRequest: Encodable, Sendable {
    let storyId: Int64
    let title: String

    enum CodingKeys: String, CodingKey {
        case storyId = "story_id"
        case title
    }
}

struct TripNoteRequest: Encodable, Sendable, Equatable {
    let storyId: Int64
    let comment: String
    let published: String
    /// The outbox retries, so a request whose answer was lost must not make
    /// a second note: the server dedupes on this key.
    let idempotencyKey: String

    enum CodingKeys: String, CodingKey {
        case storyId = "story_id"
        case comment, published
        case idempotencyKey = "idempotency_key"
    }
}

struct TripResponse: Decodable, Sendable {
    let story: TripSummary
}

struct TripListResponse: Decodable, Sendable {
    var active: [TripSummary] = []
    var history: [TripSummary] = []
    var totalHistory = 0

    enum CodingKeys: String, CodingKey {
        case active, history
        case totalHistory = "total_history"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        active = try c.value(.active, or: [])
        history = try c.value(.history, or: [])
        totalHistory = try c.value(.totalHistory, or: 0)
    }
}

struct TripEvent: Decodable, Sendable, Equatable {
    let id: Int64
    /// "journal" | "photo" | "habit" | "other"
    let type: String
    let published: String
    var comment: String?
    /// Photo events: a short-lived presigned thumbnail URL, nil until the
    /// server has made the thumbnail.
    var thumbnailUrl: String?

    enum CodingKeys: String, CodingKey {
        case id, type, published, comment
        case thumbnailUrl = "thumbnail_url"
    }
}

/// Public share link of a trip. The server builds the whole URL.
struct TripShare: Decodable, Sendable, Equatable {
    let uuid: String
    let url: String
}

struct TripShareResponse: Decodable, Sendable {
    var share: TripShare?
}

struct TripDetailResponse: Decodable, Sendable {
    let story: TripSummary
    var events: [TripEvent] = []
    /// Nil when the trip is not shared.
    var share: TripShare?

    enum CodingKeys: String, CodingKey { case story, events, share }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        story = try c.decode(TripSummary.self, forKey: .story)
        events = try c.value(.events, or: [])
        share = try c.decodeIfPresent(TripShare.self, forKey: .share)
    }
}

// MARK: - Photos

struct PhotoPresignRequest: Encodable, Sendable, Equatable {
    let storyId: Int64
    let contentType: String

    enum CodingKeys: String, CodingKey {
        case storyId = "story_id"
        case contentType = "content_type"
    }
}

struct PhotoPresignResponse: Decodable, Sendable {
    let key: String
    let uploadUrl: String

    enum CodingKeys: String, CodingKey {
        case key
        case uploadUrl = "upload_url"
    }
}

struct PhotoConfirmRequest: Encodable, Sendable, Equatable {
    let storyId: Int64
    let key: String
    let comment: String
    let contentType: String
    let published: String
    let idempotencyKey: String
    /// Hex SHA-256 of the bytes: lets the server dedup the same image within
    /// a trip even across idempotency keys (a photo picked twice).
    var contentHash: String?

    enum CodingKeys: String, CodingKey {
        case storyId = "story_id"
        case key, comment
        case contentType = "content_type"
        case published
        case idempotencyKey = "idempotency_key"
        case contentHash = "content_hash"
    }
}

/// A standalone (storyless) photo: the same two steps as a trip photo, with
/// no story. The confirm makes a photo attached to no trip.
struct StandalonePhotoPresignRequest: Encodable, Sendable, Equatable {
    let contentType: String

    enum CodingKeys: String, CodingKey { case contentType = "content_type" }
}

struct StandalonePhotoConfirmRequest: Encodable, Sendable, Equatable {
    let key: String
    let comment: String
    let contentType: String
    let published: String
    let idempotencyKey: String

    enum CodingKeys: String, CodingKey {
        case key, comment
        case contentType = "content_type"
        case published
        case idempotencyKey = "idempotency_key"
    }
}

struct PhotoOriginalResponse: Decodable, Sendable {
    let url: String
}
