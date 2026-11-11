import Foundation

/// A calendar day with no time and no zone: what the server calls a date
/// (YYYY-MM-DD).
struct Day: Hashable, Comparable, Sendable {
    let year: Int
    let month: Int
    let day: Int

    init(year: Int, month: Int, day: Int) {
        self.year = year
        self.month = month
        self.day = day
    }

    /// The day `date` falls on in the calendar's zone.
    init(_ date: Date, calendar: Calendar = .current) {
        let parts = calendar.dateComponents([.year, .month, .day], from: date)
        self.init(year: parts.year ?? 1970, month: parts.month ?? 1, day: parts.day ?? 1)
    }

    static func today(calendar: Calendar = .current) -> Day {
        Day(Date(), calendar: calendar)
    }

    var iso: String {
        String(format: "%04d-%02d-%02d", year, month, day)
    }

    /// Midnight at the start of the day.
    func start(calendar: Calendar = .current) -> Date {
        calendar.date(from: DateComponents(year: year, month: month, day: day)) ?? .distantPast
    }

    func adding(days: Int, calendar: Calendar = .current) -> Day {
        // From noon, so a day the clocks change on is still a step of one.
        let noon = calendar.date(
            from: DateComponents(year: year, month: month, day: day, hour: 12)
        ) ?? start(calendar: calendar)
        return Day(calendar.date(byAdding: .day, value: days, to: noon) ?? noon, calendar: calendar)
    }

    /// `time`'s time of day, on this day.
    func at(timeOf time: Date, calendar: Calendar = .current) -> Date {
        var parts = calendar.dateComponents([.hour, .minute, .second, .nanosecond], from: time)
        parts.year = year
        parts.month = month
        parts.day = day
        return calendar.date(from: parts) ?? time
    }

    static func < (a: Day, b: Day) -> Bool {
        (a.year, a.month, a.day) < (b.year, b.month, b.day)
    }
}

/// Full ISO 8601 timestamps, as the server sends and takes them.
enum IsoTime {

    /// e.g. 2026-05-21T15:42:33.123+02:00: the moment with the offset the
    /// device had then, so the server files it under the user's day.
    static func string(_ date: Date = Date(), timeZone: TimeZone = .current) -> String {
        date.formatted(
            Date.ISO8601FormatStyle(
                timeZoneSeparator: .colon,
                includingFractionalSeconds: true,
                timeZone: timeZone
            )
        )
    }

    static func parse(_ text: String) -> Date? {
        if let date = try? Date.ISO8601FormatStyle(includingFractionalSeconds: true).parse(text) {
            return date
        }
        return try? Date.ISO8601FormatStyle().parse(text)
    }
}

/// How the app prints a moment: 24-hour, year first, the same on every phone.
enum Stamp {

    static func dateTime(_ date: Date, timeZone: TimeZone = .current) -> String {
        "\(self.date(date, timeZone: timeZone)) \(time(date, timeZone: timeZone))"
    }

    static func date(_ date: Date, timeZone: TimeZone = .current) -> String {
        Day(date, calendar: calendar(timeZone)).iso
    }

    static func time(_ date: Date, timeZone: TimeZone = .current) -> String {
        let parts = calendar(timeZone).dateComponents([.hour, .minute], from: date)
        return String(format: "%02d:%02d", parts.hour ?? 0, parts.minute ?? 0)
    }

    static func calendar(_ timeZone: TimeZone) -> Calendar {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = timeZone
        return calendar
    }
}

extension Date {
    var epochMillis: Int64 { Int64((timeIntervalSince1970 * 1000).rounded()) }

    init(epochMillis: Int64) {
        self.init(timeIntervalSince1970: Double(epochMillis) / 1000)
    }
}
