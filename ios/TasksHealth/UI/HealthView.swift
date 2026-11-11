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
                        model.openActivitySheet(.weight)
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
        .sheet(item: $model.activitySheet) { type in
            TrackActivitySheet(model: model, initialType: type)
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

    @Environment(\.dismiss) private var dismiss
    @State private var type: ActivityType
    @State private var note = ""
    @State private var weightText = ""
    @State private var distanceText = ""
    @State private var minutes = 0
    @State private var seconds = 0

    init(model: MainModel, initialType: ActivityType) {
        self.model = model
        _type = State(initialValue: initialType)
    }

    /// A number typed with a dot or, as many keyboards have it, a comma.
    private func number(_ text: String) -> Double? {
        Double(text.trimmingCharacters(in: .whitespaces).replacingOccurrences(of: ",", with: "."))
    }

    private var canConfirm: Bool {
        switch type {
        case .weight: (number(weightText) ?? 0) > 0
        case .running: (number(distanceText) ?? 0) > 0 && (minutes > 0 || seconds > 0)
        default: true
        }
    }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 8) {
                            ForEach(ActivityType.allCases) { option in
                                FilterChip(label: "#\(option.keyword)", selected: option == type) { type = option }
                            }
                        }
                    }
                }
                Section {
                    switch type {
                    case .weight:
                        TextField("Weight (kg)", text: $weightText).keyboardType(.decimalPad)
                    case .running:
                        TextField("Distance (km)", text: $distanceText).keyboardType(.decimalPad)
                        HStack {
                            wheel("Min", $minutes, 0...240)
                            wheel("Sec", $seconds, 0...59)
                        }
                    default:
                        NoteField(placeholder: "Add a note (optional)", text: $note)
                    }
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
        switch type {
        case .weight:
            if let kg = number(weightText) { await model.trackWeight(kg: kg) }
        case .running:
            if let km = number(distanceText) {
                await model.trackRunning(distanceKm: km, minutes: minutes, seconds: seconds)
            }
        default:
            await model.trackActivity(type, note: note)
        }
    }

    /// A labelled wheel for one part of the run's time.
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
