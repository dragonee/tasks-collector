import SwiftUI

struct HealthView: View {

    @Bindable var model: MainModel
    let settings: Settings

    @State private var syncing = false

    var body: some View {
        NavigationStack {
            List {
                Section {
                    if !model.healthAvailable {
                        Text("Health data is not available on this device.")
                    } else if !model.healthAccessRequested {
                        Button("Grant access to Health") { Task { await model.requestHealthAccess() } }
                    }
                    Button(syncing ? "Syncing…" : "Sync now") {
                        Task {
                            syncing = true
                            await model.syncNow()
                            syncing = false
                        }
                    }
                    .disabled(syncing || !settings.snapshot.isConfigured || !model.healthAccessRequested)
                    Text(lastSync)
                }

                // The weight last recorded is the server's, whatever Health
                // allows. Tapping it opens the sheet on a new weight.
                Section {
                    Button {
                        model.openActivitySheet("weight")
                    } label: {
                        Text(weight).frame(maxWidth: .infinity, alignment: .leading)
                    }
                    .buttonStyle(.plain)
                }

                if model.healthAccessRequested {
                    Section("Today") {
                        if let metrics = model.todayMetrics {
                            Text("Steps: \(metrics.steps)")
                            Text(String(format: "Distance: %.1f km", metrics.distanceMeters / 1000))
                            Text("Active: \(metrics.activeMinutes) min")
                            Text(String(format: "Calories: %.0f kcal", metrics.kcal))
                        } else {
                            Text("Reading from Health…").foregroundStyle(.secondary)
                        }
                    }
                }
            }
            .navigationTitle("Health")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .primaryAction) {
                    Button("Register activity", systemImage: "plus") { model.openActivitySheet() }
                }
            }
            .refreshable { await model.refresh() }
        }
        .sheet(item: $model.activitySheet) { sheet in
            TrackActivitySheet(model: model, initialKeyword: sheet.keyword)
        }
    }

    private var lastSync: String {
        let snapshot = settings.snapshot
        if !snapshot.lastSyncError.isEmpty { return "Last sync failed: \(snapshot.lastSyncError)" }
        if snapshot.lastSyncEpochMs == 0 { return "No sync yet" }
        return "Last sync: \(Stamp.dateTime(Date(epochMillis: snapshot.lastSyncEpochMs)))"
    }

    private var weight: String {
        guard let kg = model.healthData?.weightKg else { return "No weight recorded yet" }
        let recorded = model.healthData?.recordedAt.flatMap(IsoTime.parse).map { Stamp.date($0) } ?? ""
        return String(format: "Last weight: %.1f kg (%@)", kg, recorded)
    }
}

private struct TrackActivitySheet: View {
    let model: MainModel
    let initialKeyword: String?

    @Environment(\.dismiss) private var dismiss
    @State private var chosen: String?
    @State private var note = ""
    @State private var inputs: [String: MetricInput] = [:]

    /// The keyword asked for (weight from the weight row), else the first,
    /// once the list is in.
    private var selected: HabitKeyword? {
        let keywords = model.activityKeywords
        return keywords.first { $0.keyword == (chosen ?? initialKeyword) } ?? keywords.first
    }

    private var metrics: [HabitMetric] { selected?.metrics ?? [] }

    private var values: [String: MetricValue]? { metricValues(metrics, inputs) }

    /// A habit that records something needs it, or the entry says nothing.
    private var canConfirm: Bool {
        guard selected != nil, let values else { return false }
        return metrics.isEmpty || !values.isEmpty || !note.trimmingCharacters(in: .whitespaces).isEmpty
    }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 8) {
                            ForEach(model.activityKeywords) { option in
                                FilterChip(label: "#\(option.keyword)", selected: option == selected) {
                                    chosen = option.keyword
                                    inputs = [:]
                                }
                            }
                        }
                    }
                }
                Section {
                    ForEach(metrics, id: \.key) { metric in
                        field(metric)
                    }
                    NoteField(placeholder: "Add a note (optional)", text: $note)
                    if let error = model.activityError {
                        Text(error).font(.footnote).foregroundStyle(.red)
                    }
                }
            }
            .navigationTitle("Register activity")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }.disabled(model.activitySaving)
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Track") { Task { await track() } }
                        .disabled(model.activitySaving || !canConfirm)
                }
            }
        }
        .interactiveDismissDisabled(model.activitySaving)
    }

    private func track() async {
        guard let selected, let values else { return }
        await model.trackActivity(keyword: selected.keyword, note: note, values: values)
    }

    private func input(_ key: String) -> Binding<MetricInput> {
        Binding(get: { inputs[key] ?? MetricInput() }, set: { inputs[key] = $0 })
    }

    /// The field for one metric of the habit, by its kind.
    @ViewBuilder
    private func field(_ metric: HabitMetric) -> some View {
        let label = metric.label.isEmpty ? metric.key : metric.label
        let value = input(metric.key)
        switch metric.kind {
        case "duration":
            VStack(alignment: .leading) {
                Text(label)
                HStack {
                    wheel("Min", minutes(value), 0...600)
                    wheel("Sec", seconds(value), 0...59)
                }
            }
        case "pressure":
            HStack {
                TextField("\(label) upper", text: value.first).keyboardType(.numberPad)
                TextField("lower", text: value.second).keyboardType(.numberPad)
            }
        case "money":
            HStack {
                TextField(label, text: value.first).keyboardType(.decimalPad)
                TextField("PLN", text: value.second)
                    .textInputAutocapitalization(.characters)
                    .frame(maxWidth: 70)
            }
        default:
            TextField(metric.unit.isEmpty ? label : "\(label) (\(metric.unit))", text: value.first)
                .keyboardType(metric.decimals > 0 ? .decimalPad : .numberPad)
        }
    }

    private func minutes(_ value: Binding<MetricInput>) -> Binding<Int> {
        Binding(get: { Int(value.wrappedValue.first) ?? 0 }, set: { value.wrappedValue.first = String($0) })
    }

    private func seconds(_ value: Binding<MetricInput>) -> Binding<Int> {
        Binding(get: { Int(value.wrappedValue.second) ?? 0 }, set: { value.wrappedValue.second = String($0) })
    }

    /// A labelled wheel for one part of a duration.
    private func wheel(_ label: String, _ value: Binding<Int>, _ range: ClosedRange<Int>) -> some View {
        VStack {
            Text(label).font(.footnote)
            Picker(label, selection: value) {
                ForEach(range, id: \.self) { Text("\($0)").tag($0) }
            }
            .pickerStyle(.wheel)
            .frame(height: 110)
        }
    }
}
