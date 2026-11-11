import Foundation
import HealthKit

struct BikeSession: Sendable {
    /// HealthKit's id of the workout: what keeps the 7-day re-sync from
    /// posting a ride twice.
    let id: String
    let start: Date
    let durationMinutes: Int
}

/// Reads the day's steps, distance, energy and workouts from HealthKit.
struct HealthRepository: Sendable {

    /// Steps in a minute that make it an active one. Below a brisk walk
    /// (80–100 a minute), above fidgeting at a desk: about a slow stroll.
    private static let activeStepsPerMinute = 30.0

    private let store = HKHealthStore()

    static var isAvailable: Bool { HKHealthStore.isHealthDataAvailable() }

    private var readTypes: Set<HKObjectType> {
        [
            HKQuantityType(.stepCount),
            HKQuantityType(.distanceWalkingRunning),
            HKQuantityType(.activeEnergyBurned),
            HKQuantityType(.basalEnergyBurned),
            HKObjectType.workoutType(),
        ]
    }

    /// Whether the user has been asked for access. HealthKit doesn't tell an
    /// app whether reading was allowed: a refusal reads as no data.
    func accessRequested() async -> Bool {
        guard Self.isAvailable else { return false }
        let status = try? await store.statusForAuthorizationRequest(toShare: [], read: readTypes)
        return status == .unnecessary
    }

    func requestAccess() async throws {
        try await store.requestAuthorization(toShare: [], read: readTypes)
    }

    func aggregateDay(_ day: Day, calendar: Calendar = .current) async throws -> DailyMetrics {
        let range = Self.range(of: day, calendar)
        let steps = try await sum(.stepCount, .count(), in: range) ?? 0
        let distance = try await sum(.distanceWalkingRunning, .meter(), in: range) ?? 0
        // Total energy is active plus resting. A source that writes only the
        // active part still gives a number.
        let active = try await sum(.activeEnergyBurned, .kilocalorie(), in: range)
        let resting = try await sum(.basalEnergyBurned, .kilocalorie(), in: range)
        return DailyMetrics(
            day: day,
            steps: Int(steps.rounded()),
            distanceMeters: distance,
            activeMinutes: try await activeMinutes(in: range),
            kcal: (active ?? 0) + (resting ?? 0)
        )
    }

    /// The bike rides finished on the day, each with its HealthKit id and
    /// its length in minutes, rounded.
    func bikeSessions(_ day: Day, calendar: Calendar = .current) async throws -> [BikeSession] {
        try await workouts(in: Self.range(of: day, calendar)).compactMap { workout in
            guard workout.workoutActivityType == .cycling else { return nil }
            let seconds = workout.endDate.timeIntervalSince(workout.startDate)
            let minutes = Int((seconds + 30) / 60)
            guard seconds > 0, minutes > 0 else { return nil }
            return BikeSession(id: workout.uuid.uuidString, start: workout.startDate, durationMinutes: minutes)
        }
    }

    /// Minutes of movement. A step sample often spans a long stretch (a
    /// watch writing an hour's total), so counting every minute a sample
    /// touches would call the whole hour active. Instead the day is cut
    /// into minutes, each getting its share of the steps, and those with
    /// enough steps count. Workouts are added on top, by minute, so one
    /// that overlaps the steps isn't counted twice.
    private func activeMinutes(in range: DateInterval) async throws -> Int {
        let perMinute = HKStatisticsCollectionQueryDescriptor(
            predicate: .quantitySample(type: HKQuantityType(.stepCount), predicate: Self.predicate(range)),
            options: .cumulativeSum,
            anchorDate: range.start,
            intervalComponents: DateComponents(minute: 1)
        )
        var active = Set<Int>()
        try await perMinute.result(for: store).enumerateStatistics(from: range.start, to: range.end) { minute, _ in
            let steps = minute.sumQuantity()?.doubleValue(for: .count()) ?? 0
            if steps >= Self.activeStepsPerMinute {
                active.insert(Int(minute.startDate.timeIntervalSince1970) / 60)
            }
        }
        for workout in try await workouts(in: range) where workout.endDate > workout.startDate {
            let first = Int(workout.startDate.timeIntervalSince1970) / 60
            let last = (Int(workout.endDate.timeIntervalSince1970) - 1) / 60
            if first <= last { active.formUnion(first...last) }
        }
        return active.count
    }

    private func sum(_ type: HKQuantityTypeIdentifier, _ unit: HKUnit, in range: DateInterval) async throws -> Double? {
        let query = HKStatisticsQueryDescriptor(
            predicate: .quantitySample(type: HKQuantityType(type), predicate: Self.predicate(range)),
            options: .cumulativeSum
        )
        return try await query.result(for: store)?.sumQuantity()?.doubleValue(for: unit)
    }

    private func workouts(in range: DateInterval) async throws -> [HKWorkout] {
        let query = HKSampleQueryDescriptor(
            predicates: [.workout(Self.predicate(range))],
            sortDescriptors: [SortDescriptor(\.startDate)]
        )
        return try await query.result(for: store)
    }

    private static func predicate(_ range: DateInterval) -> NSPredicate {
        HKQuery.predicateForSamples(withStart: range.start, end: range.end)
    }

    private static func range(of day: Day, _ calendar: Calendar) -> DateInterval {
        DateInterval(
            start: day.start(calendar: calendar),
            end: day.adding(days: 1, calendar: calendar).start(calendar: calendar)
        )
    }
}
