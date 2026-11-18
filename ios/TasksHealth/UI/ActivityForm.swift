import Foundation

/// What was typed for one metric in the activity sheet, as text: a number;
/// minutes and seconds; upper and lower; an amount and a currency.
struct MetricInput: Equatable, Sendable {
    var first = ""
    var second = ""
}

/// The values to send for what was typed in the activity sheet, by key; a
/// metric left empty is left out. Nil when one is filled in wrong, which
/// keeps the sheet from sending.
func metricValues(_ metrics: [HabitMetric], _ inputs: [String: MetricInput]) -> [String: MetricValue]? {
    var values: [String: MetricValue] = [:]
    for metric in metrics {
        guard let input = inputs[metric.key] else { continue }
        let first = input.first.trimmingCharacters(in: .whitespaces)
        let second = input.second.trimmingCharacters(in: .whitespaces)
        if first.isEmpty && second.isEmpty { continue }
        switch metric.kind {
        case "duration":
            guard let minutes = Int(first.isEmpty ? "0" : first),
                  let seconds = Int(second.isEmpty ? "0" : second),
                  minutes >= 0, (0...59).contains(seconds) else { return nil }
            if minutes == 0 && seconds == 0 { continue }
            values[metric.key] = .seconds(minutes * 60 + seconds)
        case "pressure":
            guard let upper = Int(first), let lower = Int(second), lower > 0, upper > lower else { return nil }
            values[metric.key] = .pressure(upper: upper, lower: lower)
        case "money":
            let currency = (second.isEmpty ? "PLN" : second).uppercased()
            guard let amount = number(first),
                  currency.count == 3, currency.allSatisfy({ $0.isASCII && $0.isUppercase }) else { return nil }
            values[metric.key] = .money(amount: amount, currency: currency)
        default:
            guard let value = number(first) else { return nil }
            values[metric.key] = .number(value)
        }
    }
    return values
}

/// The note of an activity: its hashtag, then what was written.
func activityNote(keyword: String, note: String) -> String {
    let trimmed = note.trimmingCharacters(in: .whitespacesAndNewlines)
    return trimmed.isEmpty ? "#\(keyword)" : "#\(keyword) \(trimmed)"
}

/// A number as typed, with a dot or, as many keyboards have it, a comma.
private func number(_ text: String) -> Double? {
    guard let value = Double(text.replacingOccurrences(of: ",", with: ".")), value.isFinite else { return nil }
    return value
}
