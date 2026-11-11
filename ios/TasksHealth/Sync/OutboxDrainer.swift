import Foundation

/// Delivery of the outbox, apart from when and where it runs (`OutboxSync`)
/// so that it can be tested with a stand-in for the server and for S3.
///
/// Each item's `id` is sent as the server's `idempotency_key`, so a retry
/// after a lost answer is exactly-once. Task calls that take no key are ones
/// the server answers the same way twice (see `sendTask`).
enum OutboxDrainer {

    /// What became of one item, with the item as it is now.
    enum Outcome: Equatable {
        /// Delivered: remove the item.
        case sent(OutboxItem)
        /// Didn't work now (network, 5xx, 401, 429): keep it and try later.
        case retry(OutboxItem, error: String)
        /// Refused (4xx): keep it, stop trying, show the user.
        case permanent(OutboxItem, error: String)
    }

    /// The PUT to S3, so tests don't touch the network. Throws on failure.
    typealias PhotoPutter = @Sendable (_ url: String, _ bytes: Data, _ contentType: String) async throws -> Void

    /// One pass over the queue: deliver what can be delivered and record on
    /// each item what became of it. Returns whether anything is left to retry.
    ///
    /// Task calls go first: they are small, and a tick should not wait
    /// behind a photo upload (they don't depend on trip writes). Among
    /// themselves they keep their order — a tick, then its untick — so one
    /// that has to wait holds back those queued after it.
    static func drain(outbox: Outbox, api: any OutboxAPI, put: PhotoPutter) async -> Bool {
        let queued = await outbox.all().filter { !$0.failedPermanently }
        var hadRetryable = false
        var tasksHeld = false
        for item in queued.filter(\.isTask) + queued.filter({ !$0.isTask }) {
            if item.isTask && tasksHeld { continue }
            switch await process(item, api: api, outbox: outbox, put: put) {
            case .sent(let sent):
                await outbox.remove(sent)
            case .retry(var kept, let error):
                kept.attempts += 1
                kept.lastError = error
                await outbox.update(kept)
                hadRetryable = true
                tasksHeld = tasksHeld || item.isTask
            case .permanent(var kept, let error):
                kept.attempts += 1
                kept.lastError = error
                kept.failedPermanently = true
                await outbox.update(kept)
            }
        }
        return hadRetryable
    }

    static func process(
        _ item: OutboxItem,
        api: any OutboxAPI,
        outbox: Outbox,
        put: PhotoPutter
    ) async -> Outcome {
        // What an item learns on the way (a photo is uploaded, a task's id
        // is known) is kept in `current`, so that a failure further on
        // reports the item as it is now and the bookkeeping doesn't write
        // the old one back over it.
        var current = item
        do {
            switch item.kind {
            case .note:
                // Notes are always of a trip; one without a story is a bug.
                guard let storyId = item.storyId else {
                    throw PermanentError(message: "note \(item.id) has no story")
                }
                try await api.addTripNote(
                    TripNoteRequest(
                        storyId: storyId,
                        comment: item.comment,
                        published: item.published,
                        idempotencyKey: item.id
                    )
                )
            case .photo:
                try await sendPhoto(&current, api: api, outbox: outbox, put: put)
            case .task:
                try await sendTask(&current, api: api, outbox: outbox)
            }
            return .sent(current)
        } catch let error as PermanentError {
            return .permanent(current, error: error.message)
        } catch let error as HTTPError {
            let message = "HTTP \(error.code)"
            return isRetryable(error.code)
                ? .retry(current, error: message)
                : .permanent(current, error: message)
        } catch let error as TransientError {
            return .retry(current, error: error.message)
        } catch let error as URLError {
            return .retry(current, error: error.localizedDescription)
        } catch {
            // Unexpected (an answer that doesn't parse): don't spin on it.
            return .permanent(current, error: error.localizedDescription)
        }
    }

    /// Presign, PUT, confirm; resumable. `uploaded` and `presignedKey` are
    /// saved only after the PUT worked, so a retry after a failed confirm
    /// goes straight to the confirm and one after a failed PUT presigns
    /// afresh.
    ///
    /// A nil `storyId` is a standalone photo (no trip): it goes through the
    /// storyless photo endpoints. Only the two API calls differ.
    private static func sendPhoto(
        _ item: inout OutboxItem,
        api: any OutboxAPI,
        outbox: Outbox,
        put: PhotoPutter
    ) async throws {
        let contentType = item.contentType ?? "image/jpeg"
        let storyId = item.storyId
        if !item.uploaded {
            guard let bytes = await outbox.photoBytes(item) else {
                throw PermanentError(message: "photo file missing for \(item.id)")
            }
            let presign = if let storyId {
                try await api.presignPhoto(PhotoPresignRequest(storyId: storyId, contentType: contentType))
            } else {
                try await api.presignStandalonePhoto(StandalonePhotoPresignRequest(contentType: contentType))
            }
            try await put(presign.uploadUrl, bytes, contentType)
            // Saved at once, so the app dying after the PUT still resumes
            // at the confirm.
            item.presignedKey = presign.key
            item.uploaded = true
            await outbox.update(item)
        }
        guard let key = item.presignedKey else {
            throw PermanentError(message: "photo \(item.id) is uploaded under no key")
        }
        if let storyId {
            try await api.addTripPhoto(
                PhotoConfirmRequest(
                    storyId: storyId,
                    key: key,
                    comment: item.comment,
                    contentType: contentType,
                    published: item.published,
                    idempotencyKey: item.id,
                    contentHash: item.contentHash
                )
            )
        } else {
            try await api.addStandalonePhoto(
                StandalonePhotoConfirmRequest(
                    key: key,
                    comment: item.comment,
                    contentType: contentType,
                    published: item.published,
                    idempotencyKey: item.id
                )
            )
        }
    }

    /// Make the call a task item stands for. Sent again after a lost answer,
    /// each call leaves things as the first one did: planning a task that is
    /// on the plan changes nothing, a completion carries the item's id as
    /// its idempotency key, and a step is taken back only from the count the
    /// user saw.
    ///
    /// A task without an id (a plain line of a plan, a task typed in before
    /// this) is named by its text on the plan of the day: planning it there
    /// gives the id. The id is written to the item before it is used, so a
    /// retry names the same task even when the call has moved it off that
    /// plan.
    private static func sendTask(_ item: inout OutboxItem, api: any OutboxAPI, outbox: Outbox) async throws {
        guard let op = item.task else {
            throw PermanentError(message: "task item \(item.id) says nothing to do")
        }

        func id() async throws -> String {
            if let known = op.task.id { return known }
            let planned = try await api.planText(PlanTextRequest(text: op.task.text, date: op.date))
            guard let id = planned.id else {
                throw PermanentError(message: "the server gave no id for \"\(op.task.text)\"")
            }
            item.task?.task.id = id
            await outbox.update(item)
            return id
        }

        switch op.type {
        case .plan:
            if let known = op.task.id {
                _ = try await api.planTask(id: known, PlanRef(date: op.date))
            } else {
                _ = try await api.planText(PlanTextRequest(text: op.task.text, date: op.date))
            }
        case .planItem:
            guard let boardId = op.boardId else {
                throw PermanentError(message: "no board for \(item.id)")
            }
            guard let itemId = op.itemId else {
                throw PermanentError(message: "no board item for \(item.id)")
            }
            _ = try await api.planItem(PlanItemRequest(boardId: boardId, itemId: itemId, date: op.date))
        case .complete:
            _ = try await api.completeTask(
                id: id(),
                TaskCompleteRequest(
                    day: op.date,
                    at: item.published,
                    note: op.note,
                    storyId: op.storyId,
                    idempotencyKey: item.id
                )
            )
        case .reopen:
            _ = try await api.reopenTask(
                id: id(),
                TaskReopenRequest(doneCount: op.task.doneCount > 0 ? op.task.doneCount : nil)
            )
        case .move:
            guard let toDate = op.toDate else {
                throw PermanentError(message: "no day to move \(item.id) to")
            }
            _ = try await api.moveTask(id: id(), TaskMoveRequest(fromDate: op.date, toDate: toDate))
        case .unplan:
            // A 404 is a task that is gone, as one nothing remembers is once
            // it is off its last plan: the answer to this call sent again.
            do {
                try await api.unplanTask(id: id(), PlanRef(date: op.date))
            } catch let error as HTTPError where error.code == 404 {}
        }
    }

    /// 401/408/429 and 5xx are worth retrying; other 4xx are permanent.
    private static func isRetryable(_ code: Int) -> Bool {
        code == 401 || code == 408 || code == 429 || code >= 500
    }
}
