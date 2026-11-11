import Foundation

struct PoiCoords: Equatable, Sendable {
    let lat: Double
    let lng: Double

    /// The coordinates with a pin on them, in Maps.
    var mapsUrl: URL? {
        let coords = String(format: "%f,%f", lat, lng)
        return URL(string: "https://maps.apple.com/?ll=\(coords)&q=\(coords)")
    }
}

struct ParsedTripNote: Equatable, Sendable {
    /// The comment without its leading "#poi lat=… lng=…" line.
    let text: String
    /// The coordinates of that line, or nil when there is none.
    let poi: PoiCoords?
}

/// Take a leading `#poi lat=<float> lng=<float>` line off a trip note and
/// give its coordinates apart, so the row can offer "Open in Maps".
///
/// Only the first line is looked at: that is where the app writes the
/// marker. One in the middle of a comment was typed by the user, and stays
/// in the text.
func parseTripNote(_ comment: String) -> ParsedTripNote {
    // Only spaces and tabs inside the marker line: \s would take the newline
    // and with it the body. Whatever follows the lng= value on that line (an
    // accuracy, a label) goes with the marker.
    let marker = #/^[ \t]*#poi[ \t]+lat=(-?\d+(?:\.\d+)?)[ \t]+lng=(-?\d+(?:\.\d+)?)[^\n]*(?:\n|$)/#
    guard let match = comment.prefixMatch(of: marker),
          let lat = Double(match.1),
          let lng = Double(match.2)
    else { return ParsedTripNote(text: comment, poi: nil) }
    // The body as the user wrote it, whitespace included.
    return ParsedTripNote(
        text: String(comment[match.range.upperBound...]),
        poi: PoiCoords(lat: lat, lng: lng)
    )
}

/// How event times are shown inside a trip: the time alone when the trip and
/// all its events fall on one local day, the date with it otherwise, so a
/// trip of several days isn't a wall of clock times.
enum EventTimeStyle: Equatable, Sendable {
    case time
    case dateTime

    static func pick(
        startedIso: String,
        stoppedIso: String?,
        eventIsos: [String],
        timeZone: TimeZone = .current
    ) -> EventTimeStyle {
        let days = Set(([startedIso, stoppedIso].compactMap { $0 } + eventIsos).map { localDay($0, timeZone) })
        return days.count <= 1 ? .time : .dateTime
    }

    func format(_ iso: String, timeZone: TimeZone = .current) -> String {
        guard let date = IsoTime.parse(iso) else { return iso }
        return switch self {
        case .time: Stamp.time(date, timeZone: timeZone)
        case .dateTime: Stamp.dateTime(date, timeZone: timeZone)
        }
    }
}

/// A trip's started → stopped range for the lists. The start always has its
/// date, so a row says when it was; the end drops the date when the trip
/// ended on the day it started. An active trip is just its start.
func formatTripRange(startedIso: String, stoppedIso: String?, timeZone: TimeZone = .current) -> String {
    guard let started = IsoTime.parse(startedIso) else { return startedIso }
    let start = Stamp.dateTime(started, timeZone: timeZone)
    guard let stoppedIso, let stopped = IsoTime.parse(stoppedIso) else { return start }
    let sameDay = Stamp.date(started, timeZone: timeZone) == Stamp.date(stopped, timeZone: timeZone)
    let end = sameDay ? Stamp.time(stopped, timeZone: timeZone) : Stamp.dateTime(stopped, timeZone: timeZone)
    return "\(start) → \(end)"
}

private func localDay(_ iso: String, _ timeZone: TimeZone) -> String {
    IsoTime.parse(iso).map { Stamp.date($0, timeZone: timeZone) } ?? iso
}
