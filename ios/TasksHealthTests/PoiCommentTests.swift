import Testing
@testable import TasksHealth

struct PoiCommentTests {

    private let fix = LocationFix(lat: 52.229676, lng: 21.012229, accuracyMeters: 5)

    @Test func prependsPoiLineWhenFixPresent() {
        #expect(composeComment(fix: fix, text: "hello") == "#poi lat=52.229676 lng=21.012229\nhello")
    }

    @Test func poiLineOnlyWhenTextBlank() {
        #expect(composeComment(fix: fix, text: "   ") == "#poi lat=52.229676 lng=21.012229")
    }

    @Test func trimmedTextWhenNoFix() {
        #expect(composeComment(fix: nil, text: "  just a caption  ") == "just a caption")
    }

    @Test func emptyWhenNoFixAndBlank() {
        #expect(composeComment(fix: nil, text: "  ") == "")
    }
}
