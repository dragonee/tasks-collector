import Observation
import SwiftUI

/// Behind the "add from board" picker: the flattened board, the MoSCoW
/// filter and what is selected, and planning the selected items for a day:
/// each becomes a task (or is the task it already has).
@MainActor
@Observable
final class BoardPickerModel {

    /// Filter id for items with no MoSCoW classification.
    nonisolated static let filterNone = "none"

    @ObservationIgnored private unowned let services: AppServices

    private(set) var items: [BoardItem] = []
    private(set) var loading = false
    var error: String?
    private(set) var configured = false
    /// Ids of the selected items.
    private(set) var selected: Set<String> = []
    /// The MoSCoW buckets shown (or `filterNone`). Empty: everything.
    private(set) var moscowFilter: Set<String> = []

    init(_ services: AppServices) {
        self.services = services
    }

    var visibleItems: [BoardItem] { Self.applyFilter(items, moscowFilter) }

    /// Only the items in the buckets of `filter`; all of them for an empty
    /// one. An item's bucket is its `moscow`, or `filterNone` without one.
    nonisolated static func applyFilter(_ items: [BoardItem], _ filter: Set<String>) -> [BoardItem] {
        guard !filter.isEmpty else { return items }
        return items.filter { filter.contains($0.moscow ?? filterNone) }
    }

    func reload() async {
        let snapshot = services.settings.snapshot
        configured = snapshot.isConfigured
        guard snapshot.isConfigured else {
            items = []
            return
        }
        loading = true
        defer { loading = false }
        do {
            items = try await TasksClient(snapshot).listBoardItems().items
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
    }

    func toggleSelection(_ itemId: String) {
        selected.formSymmetricDifference([itemId])
    }

    func toggleFilter(_ id: String) {
        moscowFilter.formSymmetricDifference([id])
    }

    /// Plan every selected item for `date`. Returns whether they were queued.
    ///
    /// Like everything done to a task on the phone, the calls are queued in
    /// the outbox (in board order, each naming its item by board and id), so
    /// the picker can close at once: Today lists what is queued for the day
    /// until the server has it, and shows a call the server refused.
    func addSelected(date: Day) async -> Bool {
        let chosen = items.filter { item in item.id.map(selected.contains) ?? false }
        guard !chosen.isEmpty else { return false }
        configured = services.settings.snapshot.isConfigured
        guard configured else {
            error = notConfiguredMessage
            return false
        }
        let published = IsoTime.string()
        for item in chosen {
            await services.outbox.enqueueTask(
                TaskOp(
                    type: .planItem,
                    task: PlannedTask(text: item.text),
                    date: date.iso,
                    boardId: item.boardId,
                    itemId: item.id
                ),
                published: published
            )
        }
        services.outboxSync.kick()
        selected = []
        return true
    }

    /// Append a free-typed unscheduled task to the board in view. Unlike
    /// `addSelected` this plans nothing: it only adds the line to the board,
    /// for something to do later. The server knows which board from the
    /// user's profile. The board is fetched again so the new line shows.
    func addUnscheduledTask(_ text: String) async {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        let snapshot = services.settings.snapshot
        configured = snapshot.isConfigured
        guard snapshot.isConfigured else {
            error = notConfiguredMessage
            return
        }
        do {
            try await TasksClient(snapshot).appendUnscheduledTask(UnscheduledTaskRequest(text: trimmed))
            error = nil
            await reload()
        } catch {
            self.error = error.localizedDescription
        }
    }
}

// MoSCoW buckets in order of priority. Ids and colours are those of the web
// frontend (tasks/assets/components/Moscow.vue); "Unclassified" stands for
// items with no marker.
private struct MoscowBucket: Identifiable {
    let id: String
    let label: String
    let color: Color
}

private let moscowBuckets = [
    MoscowBucket(id: "must", label: "Must", color: Color(red: 0xB9 / 255, green: 0x1C / 255, blue: 0x1C / 255)),
    MoscowBucket(id: "should", label: "Should", color: Color(red: 0xD9 / 255, green: 0x77 / 255, blue: 0x06 / 255)),
    MoscowBucket(id: "could", label: "Could", color: Color(red: 0x0D / 255, green: 0x94 / 255, blue: 0x88 / 255)),
    MoscowBucket(id: "wont", label: "Won't", color: Color(red: 0x64 / 255, green: 0x74 / 255, blue: 0x8B / 255)),
    MoscowBucket(id: BoardPickerModel.filterNone, label: "Unclassified", color: Color(white: 0.74)),
]

struct BoardPickerView: View {

    @State var model: BoardPickerModel
    let date: Day

    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            VStack(spacing: 8) {
                if let error = model.error {
                    ErrorBanner(message: "Error: \(error)") { model.error = nil }
                }
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        ForEach(moscowBuckets) { bucket in
                            FilterChip(label: bucket.label, selected: model.moscowFilter.contains(bucket.id)) {
                                model.toggleFilter(bucket.id)
                            }
                        }
                    }
                }
                // A new unscheduled task straight onto this board: something
                // to do later, not the same as ticking items below (which
                // plans them for the day).
                AddTaskRow(placeholder: "Add a task", enabled: model.configured) { text in
                    Task { await model.addUnscheduledTask(text) }
                }
            }
            .padding(.horizontal, 16)
            .padding(.top, 8)

            // Rows go by their place: an item may have no id, and what is
            // ticked lives in the model, by item id.
            List(Array(model.visibleItems.enumerated()), id: \.offset) { _, item in
                BoardItemRow(item: item, checked: item.id.map(model.selected.contains) ?? false) {
                    if let id = item.id { model.toggleSelection(id) }
                }
            }
            .listStyle(.plain)
            .overlay {
                if !model.configured {
                    EmptyState(text: notConfiguredMessage)
                } else if model.loading && model.items.isEmpty {
                    ProgressView()
                } else if model.items.isEmpty {
                    EmptyState(text: "This board has no items.")
                }
            }
            .navigationTitle("Add from board")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Add \(model.selected.count)") {
                        Task { if await model.addSelected(date: date) { dismiss() } }
                    }
                    .disabled(model.selected.isEmpty)
                }
            }
        }
        .task { await model.reload() }
    }
}

private struct BoardItemRow: View {
    let item: BoardItem
    let checked: Bool
    let onToggle: () -> Void

    /// Points of indent per level of the tree, up to a depth that leaves
    /// deeply nested items room to be read.
    private static let indentStep = 16.0
    private static let maxIndentDepth = 6

    var body: some View {
        Button(action: onToggle) {
            HStack(spacing: 12) {
                Image(systemName: checked ? "checkmark.square.fill" : "square")
                    .font(.title3)
                    .foregroundStyle(checked ? Color.accentColor : .secondary)
                Text(item.text)
                    .strikethrough(item.done)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.leading, Double(min(item.depth, Self.maxIndentDepth)) * Self.indentStep)
                if let bucket = moscowBuckets.first(where: { $0.id == item.moscow ?? BoardPickerModel.filterNone }) {
                    Circle().fill(bucket.color).frame(width: 12, height: 12)
                }
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}

/// A pill that is on or off.
struct FilterChip: View {
    let label: String
    let selected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Text(label)
                .font(.subheadline)
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .background(selected ? Color.accentColor.opacity(0.2) : Color.clear, in: Capsule())
                .overlay(Capsule().stroke(selected ? Color.accentColor : Color.secondary.opacity(0.5)))
        }
        .buttonStyle(.plain)
    }
}
