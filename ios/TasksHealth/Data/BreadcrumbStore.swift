import Foundation

/// One recorded location sample on a trip's breadcrumb trail.
///
/// `t` is the moment of the sample (epoch millis): what a photo is matched
/// to where it was taken by. Kept tiny: a long trip records thousands, one
/// line each.
struct Breadcrumb: Codable, Sendable, Equatable {
    let t: Int64
    let lat: Double
    let lng: Double
    var acc: Float?
}

/// Append-only local log of a trip's location breadcrumbs.
///
/// One JSON object per line in `file`, so each new sample is a cheap append
/// with no rewrite of the growing file. The location recorder is the only
/// writer; readers put up with a torn last line by parsing line by line.
struct BreadcrumbStore: Sendable {

    let file: URL

    func append(_ crumb: Breadcrumb) {
        guard var line = try? JSONEncoder().encode(crumb) else { return }
        line.append(0x0A)
        let files = FileManager.default
        try? files.createDirectory(at: file.deletingLastPathComponent(), withIntermediateDirectories: true)
        if !files.fileExists(atPath: file.path) {
            files.createFile(atPath: file.path, contents: nil)
        }
        guard let handle = try? FileHandle(forWritingTo: file) else { return }
        defer { try? handle.close() }
        _ = try? handle.seekToEnd()
        try? handle.write(contentsOf: line)
    }

    /// All breadcrumbs, oldest first. Skips a line that doesn't parse.
    func all() -> [Breadcrumb] {
        guard let text = try? String(contentsOf: file, encoding: .utf8) else { return [] }
        let decoder = JSONDecoder()
        return text.split(whereSeparator: \.isNewline)
            .compactMap { try? decoder.decode(Breadcrumb.self, from: Data($0.utf8)) }
            .sorted { $0.t < $1.t }
    }

    func clear() {
        try? FileManager.default.removeItem(at: file)
    }
}
