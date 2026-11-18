import Foundation
import Testing
@testable import TasksHealth

struct ActivityFormTests {

    private let weight = HabitMetric(key: "weight", kind: "number", unit: "kg", decimals: 1)
    private let duration = HabitMetric(key: "duration", kind: "duration")
    private let pressure = HabitMetric(key: "pressure", kind: "pressure")
    private let amount = HabitMetric(key: "amount", kind: "money")

    @Test func eachKindIsSentAsTheServerTakesIt() throws {
        let values = metricValues(
            [weight, duration, pressure, amount],
            [
                "weight": MetricInput(first: "80,5"),
                "duration": MetricInput(first: "25", second: "25"),
                "pressure": MetricInput(first: "120", second: "80"),
                "amount": MetricInput(first: "90", second: "eur"),
            ]
        )
        #expect(values == [
            "weight": .number(80.5),
            "duration": .seconds(1525),
            "pressure": .pressure(upper: 120, lower: 80),
            "amount": .money(amount: 90, currency: "EUR"),
        ])

        let encoder = JSONEncoder()
        encoder.outputFormatting = .sortedKeys
        let json = String(decoding: try encoder.encode(values!), as: UTF8.self)
        #expect(json == #"{"amount":{"amount":90,"currency":"EUR"},"duration":1525,"pressure":[120,80],"weight":80.5}"#)
    }

    @Test func aMetricLeftEmptyIsLeftOut() {
        let values = metricValues(
            [weight, duration, amount],
            ["weight": MetricInput(first: "80"), "duration": MetricInput(first: "0", second: "0")]
        )
        #expect(values == ["weight": .number(80)])
    }

    @Test func moneyWithoutACurrencyIsInZloty() {
        #expect(metricValues([amount], ["amount": MetricInput(first: "45")]) == ["amount": .money(amount: 45, currency: "PLN")])
    }

    @Test func somethingFilledInWrongKeepsTheSheetFromSending() {
        #expect(metricValues([weight], ["weight": MetricInput(first: "heavy")]) == nil)
        #expect(metricValues([pressure], ["pressure": MetricInput(first: "80", second: "120")]) == nil)
        #expect(metricValues([pressure], ["pressure": MetricInput(first: "120")]) == nil)
        #expect(metricValues([amount], ["amount": MetricInput(first: "90", second: "euro")]) == nil)
    }

    @Test func theNoteIsTheHashtagAndWhatWasWritten() {
        #expect(activityNote(keyword: "running", note: "  ") == "#running")
        #expect(activityNote(keyword: "running", note: " park ") == "#running park")
    }

    @Test func aKeywordComesWithItsHabitsMetrics() throws {
        let json = #"""
        [{"id": 1, "keyword": "running", "habit": {"id": 3, "name": "Workout",
          "metrics": [{"key": "distance", "label": "Distance", "kind": "number", "unit": "km", "decimals": 1}]}},
         {"id": 2, "keyword": "food", "habit": null}]
        """#
        let keywords = try JSONDecoder().decode([HabitKeyword].self, from: Data(json.utf8))
        #expect(keywords[0].metrics == [HabitMetric(key: "distance", label: "Distance", kind: "number", unit: "km", decimals: 1)])
        #expect(keywords[1].metrics.isEmpty)
    }
}
