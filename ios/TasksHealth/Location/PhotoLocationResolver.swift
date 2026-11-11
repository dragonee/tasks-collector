import Foundation

struct LocationFix: Equatable, Sendable {
    let lat: Double
    let lng: Double
    var accuracyMeters: Float?
}

/// Where a ready fix came from: a live GPS read (notes and standalone photos,
/// recorded "now") or the trip's recorded breadcrumb track (trip photos,
/// located at the time they were taken).
enum GpsSource: Sendable {
    case live
    case track
}

/// Where finding a location stands, for the add-note and add-photo sheets:
/// whether "Save with location" can be offered, and what hint to show.
enum GpsState: Equatable, Sendable {
    case idle
    case waiting
    /// `at` (track only): when the photo was taken, shown in the hint.
    case ready(LocationFix, source: GpsSource = .live, at: Date? = nil)
    case denied
    case unavailable

    var fix: LocationFix? {
        if case .ready(let fix, _, _) = self { fix } else { nil }
    }
}

/// A journal comment made of an optional location and the user's text. With
/// a fix, a `#poi lat=… lng=…` line goes first (the server parses it into a
/// HabitTracked); without one the trimmed text is used as it is. Shared by
/// trip notes, trip photos and standalone photos, so the marker is the same
/// in all of them.
func composeComment(fix: LocationFix?, text: String) -> String {
    let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
    guard let fix else { return trimmed }
    let prefix = String(format: "#poi lat=%.6f lng=%.6f", fix.lat, fix.lng)
    return trimmed.isEmpty ? prefix : "\(prefix)\n\(trimmed)"
}

/// A photo's location from a trip's breadcrumb trail, by the time the photo
/// was taken — so photos can be picked and uploaded long after (and far
/// from) where they were taken and still get the right coordinates.
///
/// Take the breadcrumbs just before and just after the capture time.
///  - If the nearer one is within `directMatch`, use it.
///  - Otherwise the capture time sits in a gap in the tracking; trust it
///    only if the two points around it are less than `stationaryMeters`
///    apart (the user stayed in one place), and use the one closer in time.
///    Never interpolate across a move: nil, and the photo goes without a
///    location.
enum PhotoLocationResolver {

    private static let directMatchMs: Int64 = 2 * 60 * 1000
    private static let stationaryMeters = 200.0

    static func resolve(_ breadcrumbs: [Breadcrumb], captureMs: Int64) -> LocationFix? {
        let before = breadcrumbs.filter { $0.t <= captureMs }.max { $0.t < $1.t }
        let after = breadcrumbs.filter { $0.t >= captureMs }.min { $0.t < $1.t }
        guard let nearest = closer(before, after, to: captureMs) else { return nil }

        if abs(nearest.t - captureMs) <= directMatchMs {
            return fix(nearest)
        }
        if let before, let after,
           haversineMeters(before.lat, before.lng, after.lat, after.lng) < stationaryMeters {
            return fix(nearest)
        }
        return nil
    }

    private static func closer(_ a: Breadcrumb?, _ b: Breadcrumb?, to t: Int64) -> Breadcrumb? {
        guard let a else { return b }
        guard let b else { return a }
        return abs(a.t - t) <= abs(b.t - t) ? a : b
    }

    private static func fix(_ crumb: Breadcrumb) -> LocationFix {
        LocationFix(lat: crumb.lat, lng: crumb.lng, accuracyMeters: crumb.acc)
    }

    /// Great-circle distance in metres between two points.
    static func haversineMeters(_ lat1: Double, _ lng1: Double, _ lat2: Double, _ lng2: Double) -> Double {
        let earthRadius = 6_371_000.0
        func radians(_ degrees: Double) -> Double { degrees * .pi / 180 }
        let dLat = radians(lat2 - lat1)
        let dLng = radians(lng2 - lng1)
        let a = pow(sin(dLat / 2), 2)
            + cos(radians(lat1)) * cos(radians(lat2)) * pow(sin(dLng / 2), 2)
        return 2 * earthRadius * asin(min(1, sqrt(a)))
    }
}
