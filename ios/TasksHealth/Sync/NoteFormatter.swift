import Foundation

/// A day's totals, as read from HealthKit.
struct DailyMetrics: Equatable, Sendable {
    let day: Day
    let steps: Int
    let distanceMeters: Double
    let activeMinutes: Int
    let kcal: Double
}

enum NoteFormatter {

    /// The note of the day's daily-health entry, e.g.
    /// `steps=8520 distance=6.2km active=42min kcal=2150`.
    static func format(_ metrics: DailyMetrics) -> String {
        let distance = String(format: "%.1f", metrics.distanceMeters / 1000)
        let kcal = String(format: "%.0f", metrics.kcal)
        return "steps=\(metrics.steps) distance=\(distance)km active=\(metrics.activeMinutes)min kcal=\(kcal)"
    }
}
