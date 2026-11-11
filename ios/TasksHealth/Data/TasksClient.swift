import Foundation

/// The server answered, and not with a 2xx.
struct HTTPError: LocalizedError, Equatable {
    let code: Int

    var errorDescription: String? { "HTTP \(code)" }
}

/// Something that didn't work now and may well work later (a refused upload,
/// a server that can't be reached): worth trying again.
struct TransientError: LocalizedError, Equatable {
    let message: String

    var errorDescription: String? { message }
}

/// Something that won't work however often it is tried.
struct PermanentError: LocalizedError, Equatable {
    let message: String

    var errorDescription: String? { message }
}

/// The calls the outbox makes (see `OutboxDrainer`), apart from the rest so
/// tests can stand in for the server.
protocol OutboxAPI: Sendable {
    func addTripNote(_ body: TripNoteRequest) async throws
    func presignPhoto(_ body: PhotoPresignRequest) async throws -> PhotoPresignResponse
    func addTripPhoto(_ body: PhotoConfirmRequest) async throws
    func presignStandalonePhoto(_ body: StandalonePhotoPresignRequest) async throws -> PhotoPresignResponse
    func addStandalonePhoto(_ body: StandalonePhotoConfirmRequest) async throws
    func planText(_ body: PlanTextRequest) async throws -> PlannedTask
    func planItem(_ body: PlanItemRequest) async throws -> PlannedTask
    func planTask(id: String, _ body: PlanRef) async throws -> PlannedTask
    func unplanTask(id: String, _ body: PlanRef) async throws
    func moveTask(id: String, _ body: TaskMoveRequest) async throws -> PlannedTask
    func completeTask(id: String, _ body: TaskCompleteRequest) async throws -> PlannedTask
    func reopenTask(id: String, _ body: TaskReopenRequest) async throws -> PlannedTask
}

/// The server's API, as the user a token stands for.
struct TasksClient: OutboxAPI {

    private let base: String
    private let token: String

    init(serverUrl: String, apiToken: String) throws {
        let trimmed = Self.trimmed(serverUrl)
        guard let url = URL(string: trimmed), url.scheme?.hasPrefix("http") == true, url.host != nil else {
            throw PermanentError(message: "\"\(serverUrl)\" is not a server URL.")
        }
        base = trimmed + "/"
        token = apiToken
    }

    init(_ snapshot: SettingsSnapshot) throws {
        try self.init(serverUrl: snapshot.serverUrl, apiToken: snapshot.apiToken)
    }

    // MARK: Habits and health

    func trackHabit(_ body: TrackHabitRequest) async throws {
        try await post("api/v1/habit/track/", body)
    }

    /// A web endpoint (no api/v1/) that takes a free-form habit line and
    /// makes one HabitTracked per hashtag: for things that happen several
    /// times a day, which api/v1/habit/track/ would fold into one.
    func trackHabitText(_ body: TrackHabitTextRequest) async throws {
        try await post("habit/track/", body)
    }

    /// The keywords the user can track on `date`: those of their profile,
    /// without the habits already tracked that day.
    func listHabitKeywords(date: String) async throws -> [HabitKeyword] {
        try await get("habit/keywords/mine/", query: ["date": date])
    }

    func healthData() async throws -> HealthDataResponse {
        try await get("api/v1/android/health/data/")
    }

    // MARK: Tasks and the board

    func agenda(date: String) async throws -> AgendaResponse {
        try await get("api/v1/tasks/agenda/", query: ["date": date])
    }

    /// The current board flattened (pre-order, with depths), for the "add
    /// from board" picker.
    func listBoardItems() async throws -> BoardItemsResponse {
        try await get("api/v1/android/board/items/")
    }

    func appendUnscheduledTask(_ body: UnscheduledTaskRequest) async throws {
        try await post("boards/append/", body)
    }

    func planText(_ body: PlanTextRequest) async throws -> PlannedTask {
        try await post("api/v1/tasks/", body)
    }

    func planItem(_ body: PlanItemRequest) async throws -> PlannedTask {
        try await post("api/v1/tasks/", body)
    }

    /// Put a task on another of the user's plans as well.
    func planTask(id: String, _ body: PlanRef) async throws -> PlannedTask {
        try await post("api/v1/tasks/\(id)/plan/", body)
    }

    /// Take a task off a plan. 204 when nothing remembers it and it is gone,
    /// else the task; either way there is nothing to read.
    func unplanTask(id: String, _ body: PlanRef) async throws {
        try await post("api/v1/tasks/\(id)/unplan/", body)
    }

    func moveTask(id: String, _ body: TaskMoveRequest) async throws -> PlannedTask {
        try await post("api/v1/tasks/\(id)/move/", body)
    }

    func completeTask(id: String, _ body: TaskCompleteRequest) async throws -> PlannedTask {
        try await post("api/v1/tasks/\(id)/complete/", body)
    }

    /// Take back the last step done.
    func reopenTask(id: String, _ body: TaskReopenRequest) async throws -> PlannedTask {
        try await post("api/v1/tasks/\(id)/reopen/", body)
    }

    // MARK: Trips

    func startTrip(_ body: TripStartRequest) async throws -> TripResponse {
        try await post("api/v1/android/trip/start/", body)
    }

    func stopTrip(_ body: TripStopRequest) async throws {
        try await post("api/v1/android/trip/stop/", body)
    }

    func updateTrip(_ body: TripUpdateRequest) async throws {
        try await post("api/v1/android/trip/update/", body)
    }

    func shareTrip(_ body: TripStoryIdRequest) async throws -> TripShareResponse {
        try await post("api/v1/android/trip/share/", body)
    }

    func revokeTripShare(_ body: TripStoryIdRequest) async throws {
        try await post("api/v1/android/trip/share/revoke/", body)
    }

    func addTripNote(_ body: TripNoteRequest) async throws {
        try await post("api/v1/android/trip/note/", body)
    }

    func listTrips(page: Int = 1, pageSize: Int = 20) async throws -> TripListResponse {
        try await get(
            "api/v1/android/trip/list/",
            query: ["page": String(page), "page_size": String(pageSize)]
        )
    }

    func tripDetail(storyId: Int64) async throws -> TripDetailResponse {
        try await get("api/v1/android/trip/\(storyId)/")
    }

    // MARK: Photos

    func presignPhoto(_ body: PhotoPresignRequest) async throws -> PhotoPresignResponse {
        try await post("api/v1/android/trip/photo/presign/", body)
    }

    func addTripPhoto(_ body: PhotoConfirmRequest) async throws {
        try await post("api/v1/android/trip/photo/", body)
    }

    func photoOriginal(eventId: Int64) async throws -> PhotoOriginalResponse {
        try await get("api/v1/android/trip/photo/\(eventId)/original/")
    }

    func presignStandalonePhoto(_ body: StandalonePhotoPresignRequest) async throws -> PhotoPresignResponse {
        try await post("api/v1/android/photo/presign/", body)
    }

    func addStandalonePhoto(_ body: StandalonePhotoConfirmRequest) async throws {
        try await post("api/v1/android/photo/", body)
    }

    // MARK: Requests

    private func get<Out: Decodable>(_ path: String, query: [String: String] = [:]) async throws -> Out {
        try decode(await send("GET", path, query: query, body: nil))
    }

    private func post<Out: Decodable>(_ path: String, _ body: some Encodable) async throws -> Out {
        try decode(await send("POST", path, body: JSONEncoder().encode(body)))
    }

    /// A POST whose answer nobody reads.
    private func post(_ path: String, _ body: some Encodable) async throws {
        _ = try await send("POST", path, body: JSONEncoder().encode(body))
    }

    private func decode<Out: Decodable>(_ data: Data) throws -> Out {
        try JSONDecoder().decode(Out.self, from: data)
    }

    private func send(
        _ method: String,
        _ path: String,
        query: [String: String] = [:],
        body: Data?
    ) async throws -> Data {
        guard var components = URLComponents(string: base + path) else {
            throw PermanentError(message: "bad path \(path)")
        }
        if !query.isEmpty {
            components.queryItems = query.sorted { $0.key < $1.key }.map {
                URLQueryItem(name: $0.key, value: $0.value)
            }
        }
        guard let url = components.url else {
            throw PermanentError(message: "bad path \(path)")
        }
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("Token \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if let body {
            request.httpBody = body
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        return try await Self.perform(request)
    }

    // MARK: Without a token

    // These must not carry the "Authorization: Token …" header: S3 refuses
    // auth it doesn't expect (and the token would leak to the bucket's host),
    // and logging in and out is done without a token, or to get rid of one.

    /// Upload bytes to a presigned PUT URL.
    static func putToPresignedUrl(_ url: String, _ bytes: Data, contentType: String) async throws {
        guard let target = URL(string: url) else {
            throw PermanentError(message: "the server sent no upload URL")
        }
        var request = URLRequest(url: target)
        request.httpMethod = "PUT"
        request.setValue(contentType, forHTTPHeaderField: "Content-Type")
        let (_, response) = try await URLSession.shared.upload(for: request, from: bytes)
        let code = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard (200..<300).contains(code) else {
            throw TransientError(message: "photo upload failed: HTTP \(code)")
        }
    }

    /// Trade the code of a login for the app's token (see `OAuthLogin`).
    /// Throws when the server refuses, with what it said.
    static func exchangeCode(_ pending: OAuthLogin.Pending, code: String, redirectUri: String) async throws -> String {
        let request = try form(
            "\(pending.serverUrl)/oauth/token/",
            [
                ("grant_type", "authorization_code"),
                ("code", code),
                ("code_verifier", pending.verifier),
                ("client_id", OAuthLogin.clientId),
                ("redirect_uri", redirectUri),
            ]
        )
        let (data, response) = try await URLSession.shared.data(for: request)
        let code = (response as? HTTPURLResponse)?.statusCode ?? 0
        let answer = try? JSONDecoder().decode(TokenAnswer.self, from: data)
        guard (200..<300).contains(code) else {
            throw PermanentError(message: "login refused: \(answer?.error ?? "HTTP \(code)")")
        }
        guard let token = answer?.accessToken, !token.isEmpty else {
            throw PermanentError(message: "the server sent no token")
        }
        return token
    }

    /// Tell the server to forget a token: the app logging out. Throws when
    /// the server can't be told.
    static func revokeToken(serverUrl: String, apiToken: String) async throws {
        let request = try form("\(trimmed(serverUrl))/oauth/revoke/", [("token", apiToken)])
        let (_, response) = try await URLSession.shared.data(for: request)
        let code = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard (200..<300).contains(code) else {
            throw TransientError(message: "logout failed: HTTP \(code)")
        }
    }

    private struct TokenAnswer: Decodable {
        var accessToken: String?
        var error: String?

        enum CodingKeys: String, CodingKey {
            case accessToken = "access_token"
            case error
        }
    }

    private static func form(_ url: String, _ fields: [(String, String)]) throws -> URLRequest {
        guard let target = URL(string: url) else {
            throw PermanentError(message: "\"\(url)\" is not a server URL.")
        }
        var unreserved = CharacterSet.alphanumerics
        unreserved.insert(charactersIn: "-._~")
        let body = fields.map { name, value in
            "\(name)=\(value.addingPercentEncoding(withAllowedCharacters: unreserved) ?? "")"
        }.joined(separator: "&")
        var request = URLRequest(url: target)
        request.httpMethod = "POST"
        request.httpBody = Data(body.utf8)
        request.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        return request
    }

    private static func perform(_ request: URLRequest) async throws -> Data {
        let (data, response) = try await URLSession.shared.data(for: request)
        let code = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard (200..<300).contains(code) else { throw HTTPError(code: code) }
        return data
    }

    static func trimmed(_ serverUrl: String) -> String {
        var url = serverUrl.trimmingCharacters(in: .whitespacesAndNewlines)
        while url.hasSuffix("/") { url.removeLast() }
        return url
    }
}
