import Testing
@testable import TasksHealth

struct NoteFormatterTests {

    private func metrics(steps: Int, distanceMeters: Double, activeMinutes: Int, kcal: Double) -> DailyMetrics {
        DailyMetrics(
            day: Day(year: 2026, month: 5, day: 17),
            steps: steps,
            distanceMeters: distanceMeters,
            activeMinutes: activeMinutes,
            kcal: kcal
        )
    }

    @Test func formatsAllFourMetrics() {
        let note = NoteFormatter.format(
            metrics(steps: 8520, distanceMeters: 6234.5, activeMinutes: 42, kcal: 1499.4)
        )
        #expect(note == "steps=8520 distance=6.2km active=42min kcal=1499")
    }

    @Test func zeroMetricsStillRenderWithZeroValues() {
        let note = NoteFormatter.format(metrics(steps: 0, distanceMeters: 0, activeMinutes: 0, kcal: 0))
        #expect(note == "steps=0 distance=0.0km active=0min kcal=0")
    }

    @Test func distanceIsRenderedWithOneDecimalInKmUsingUsLocale() {
        let note = NoteFormatter.format(metrics(steps: 1, distanceMeters: 1234, activeMinutes: 0, kcal: 0))
        #expect(note == "steps=1 distance=1.2km active=0min kcal=0")
    }

    @Test func bikeRideNoteCarriesHashtagDurationAndNoDistance() {
        let text = NoteFormatter.formatBikeRide(keyword: "workout", durationMinutes: 45)
        #expect(text == "#workout Bike ride (duration=45 min)")
    }

    @Test func kcalIsRoundedToWholeNumber() {
        let note = NoteFormatter.format(metrics(steps: 0, distanceMeters: 0, activeMinutes: 0, kcal: 1499.6))
        #expect(note == "steps=0 distance=0.0km active=0min kcal=1500")
    }
}
