import ImageIO
import PhotosUI
import SwiftUI
import UniformTypeIdentifiers

/// A photo picked from the library: its bytes as they will be uploaded.
struct PickedPhoto: Sendable, Equatable {
    let data: Data
    let contentType: String
    /// When it was taken, by its EXIF; nil when the file doesn't say. The
    /// server reads the same EXIF and goes by it when it is there.
    let taken: Date?

    /// When it was taken as far as the app knows: by its EXIF, else now.
    var takenOrNow: Date { taken ?? Date() }
}

enum PhotoLoader {

    /// Read a picked photo. The bytes are read now: the picker's item is
    /// good for this session only.
    static func load(_ item: PhotosPickerItem) async throws -> PickedPhoto {
        guard let data = try await item.loadTransferable(type: Data.self) else {
            throw PermanentError(message: "could not read the selected photo")
        }
        return PickedPhoto(data: data, contentType: contentType(of: data), taken: takenAt(data))
    }

    /// The MIME type of image bytes, by what they are rather than by what
    /// the picker called them (it may convert on the way).
    static func contentType(of data: Data) -> String {
        guard let source = CGImageSourceCreateWithData(data as CFData, nil),
              let identifier = CGImageSourceGetType(source) as String?,
              let mime = UTType(identifier)?.preferredMIMEType
        else { return "image/jpeg" }
        return mime
    }

    static func takenAt(_ data: Data, timeZone: TimeZone = .current) -> Date? {
        guard let source = CGImageSourceCreateWithData(data as CFData, nil),
              let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any],
              let exif = properties[kCGImagePropertyExifDictionary] as? [CFString: Any],
              let stamp = exif[kCGImagePropertyExifDateTimeOriginal] as? String
        else { return nil }
        return parseExif(
            stamp,
            offset: exif[kCGImagePropertyExifOffsetTimeOriginal] as? String,
            timeZone: timeZone
        )
    }

    /// An EXIF time, "2026:05:21 15:42:33", in the zone its `offset`
    /// ("+02:00") names; in `timeZone` when the camera wrote none.
    static func parseExif(_ stamp: String, offset: String?, timeZone: TimeZone) -> Date? {
        let parts = stamp.split(whereSeparator: { !$0.isNumber }).compactMap { Int($0) }
        guard parts.count >= 6 else { return nil }
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = offset.flatMap(zone) ?? timeZone
        return calendar.date(
            from: DateComponents(
                year: parts[0], month: parts[1], day: parts[2],
                hour: parts[3], minute: parts[4], second: parts[5]
            )
        )
    }

    private static func zone(_ offset: String) -> TimeZone? {
        guard let sign = offset.first, sign == "+" || sign == "-" else { return nil }
        let parts = offset.dropFirst().split(separator: ":").compactMap { Int($0) }
        guard parts.count == 2 else { return nil }
        return TimeZone(secondsFromGMT: (sign == "-" ? -1 : 1) * (parts[0] * 3600 + parts[1] * 60))
    }

    /// A small copy of an image for a row or a sheet: a photo off the
    /// camera is far larger than anything shown here.
    static func thumbnail(_ source: LocalImage.Source, maxPixel: Int) -> UIImage? {
        let image = switch source {
        case .data(let data): CGImageSourceCreateWithData(data as CFData, nil)
        case .file(let url): CGImageSourceCreateWithURL(url as CFURL, nil)
        }
        let options: [CFString: Any] = [
            kCGImageSourceCreateThumbnailFromImageAlways: true,
            kCGImageSourceCreateThumbnailWithTransform: true,
            kCGImageSourceThumbnailMaxPixelSize: maxPixel,
        ]
        guard let image, let small = CGImageSourceCreateThumbnailAtIndex(image, 0, options as CFDictionary) else {
            return nil
        }
        return UIImage(cgImage: small)
    }
}

/// An image the phone has itself (picked, or waiting in the outbox), shown
/// whole.
struct LocalImage: View {
    enum Source: Equatable, Sendable {
        case data(Data)
        case file(URL)
    }

    let source: Source
    @State private var image: UIImage?

    var body: some View {
        Group {
            if let image {
                Image(uiImage: image).resizable().scaledToFit()
            } else {
                Color.secondary.opacity(0.15)
            }
        }
        .task(id: source) {
            let source = source
            image = await Task.detached { PhotoLoader.thumbnail(source, maxPixel: 1200) }.value
        }
    }
}
