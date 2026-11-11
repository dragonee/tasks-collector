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

    /// The note of the day's `health-metrics` habit, e.g.
    /// `steps=8520 distance=6.2km active=42min kcal=2150`.
    static func format(_ metrics: DailyMetrics) -> String {
        let distance = String(format: "%.1f", metrics.distanceMeters / 1000)
        let kcal = String(format: "%.0f", metrics.kcal)
        return "steps=\(metrics.steps) distance=\(distance)km active=\(metrics.activeMinutes)min kcal=\(kcal)"
    }

    /// A bike ride as a habit line that the server's hashtag parser turns
    /// into a HabitTracked of the `keyword` habit. No distance: a ride
    /// recorded by the phone alone has none to trust.
    static func formatBikeRide(keyword: String, durationMinutes: Int) -> String {
        "#\(keyword) Bike ride (duration=\(durationMinutes) min)"
    }
}
