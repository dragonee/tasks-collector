import Foundation
import Testing
@testable import TasksHealth

struct TripNoteFormatTests {

    private let utc = TimeZone.gmt

    // MARK: parseTripNote

    @Test func parsesLeadingPoiLineAndStripsItFromText() {
        let parsed = parseTripNote("#poi lat=40.7128 lng=-74.0060\nCoffee at the corner")
        #expect(parsed.text == "Coffee at the corner")
        #expect(parsed.poi?.lat == 40.7128)
        #expect(parsed.poi?.lng == -74.0060)
    }

    @Test func parsesPoiLineOnItsOwnWithNoBody() {
        let parsed = parseTripNote("#poi lat=10.0 lng=20.0")
        #expect(parsed.text == "")
        #expect(parsed.poi != nil)
    }

    @Test func leavesCommentAloneWhenNoPoiLineIsPresent() {
        let parsed = parseTripNote("Plain note without coordinates")
        #expect(parsed.text == "Plain note without coordinates")
        #expect(parsed.poi == nil)
    }

    @Test func doesNotStripPoiMentionFromInsideTheBody() {
        let parsed = parseTripNote("Saw a #poi sign here\nbut no coords")
        #expect(parsed.text == "Saw a #poi sign here\nbut no coords")
        #expect(parsed.poi == nil)
    }

    @Test func acceptsNegativeCoordinates() {
        let parsed = parseTripNote("#poi lat=-33.8688 lng=151.2093\nSydney")
        #expect(parsed.poi?.lat == -33.8688)
        #expect(parsed.poi?.lng == 151.2093)
    }

    @Test func preservesMultiLineBodyVerbatim() {
        let parsed = parseTripNote("#poi lat=1 lng=2\nFirst line\n\nThird line  with trailing  ")
        #expect(parsed.text == "First line\n\nThird line  with trailing  ")
    }

    @Test func toleratesExtraTextOnThePoiLineItself() {
        // A later client may add an accuracy, an altitude or a label to the
        // line; the body still starts on the next one.
        let parsed = parseTripNote("#poi lat=10 lng=20 acc=5\nThe note body stays whole")
        #expect(parsed.text == "The note body stays whole")
        #expect(parsed.poi?.lat == 10)
        #expect(parsed.poi?.lng == 20)
    }

    // MARK: EventTimeStyle

    @Test func singleDayTripUsesTimeOnly() {
        let style = EventTimeStyle.pick(
            startedIso: "2026-05-25T10:00:00Z",
            stoppedIso: "2026-05-25T18:00:00Z",
            eventIsos: ["2026-05-25T11:00:00Z", "2026-05-25T17:30:00Z"],
            timeZone: utc
        )
        #expect(style == .time)
        #expect(style.format("2026-05-25T11:00:00Z", timeZone: utc) == "11:00")
        // No date in it.
        #expect(!style.format("2026-05-25T17:30:00Z", timeZone: utc).contains("-"))
    }

    @Test func multiDayTripUsesFullDateTime() {
        let style = EventTimeStyle.pick(
            startedIso: "2026-05-25T10:00:00Z",
            stoppedIso: "2026-05-27T18:00:00Z",
            eventIsos: ["2026-05-25T11:00:00Z", "2026-05-26T14:00:00Z"],
            timeZone: utc
        )
        #expect(style == .dateTime)
        #expect(style.format("2026-05-26T14:00:00Z", timeZone: utc) == "2026-05-26 14:00")
    }

    @Test func activeTripWithNoStoppedStillPicksSingleDayWhenEventsFit() {
        let style = EventTimeStyle.pick(
            startedIso: "2026-05-25T08:00:00Z",
            stoppedIso: nil,
            eventIsos: ["2026-05-25T12:00:00Z"],
            timeZone: utc
        )
        #expect(style.format("2026-05-25T12:00:00Z", timeZone: utc) == "12:00")
    }

    @Test func activeTripSpanningIntoANewDayFlipsToFullDateTime() {
        let style = EventTimeStyle.pick(
            startedIso: "2026-05-25T22:00:00Z",
            stoppedIso: nil,
            eventIsos: ["2026-05-25T23:00:00Z", "2026-05-26T01:00:00Z"],
            timeZone: utc
        )
        #expect(style.format("2026-05-25T23:00:00Z", timeZone: utc) == "2026-05-25 23:00")
        #expect(style.format("2026-05-26T01:00:00Z", timeZone: utc) == "2026-05-26 01:00")
    }

    // MARK: formatTripRange

    @Test func activeTripRangeShowsOnlyTheStartDatetime() {
        let range = formatTripRange(startedIso: "2026-05-25T10:00:00Z", stoppedIso: nil, timeZone: utc)
        #expect(range == "2026-05-25 10:00")
    }

    @Test func singleDayCompletedTripOmitsTheDateOnTheEndSide() {
        let range = formatTripRange(
            startedIso: "2026-05-25T10:00:00Z", stoppedIso: "2026-05-25T18:30:00Z", timeZone: utc
        )
        #expect(range == "2026-05-25 10:00 → 18:30")
    }

    @Test func multiDayCompletedTripRepeatsTheDateOnBothSides() {
        let range = formatTripRange(
            startedIso: "2026-05-25T22:00:00Z", stoppedIso: "2026-05-27T03:15:00Z", timeZone: utc
        )
        #expect(range == "2026-05-25 22:00 → 2026-05-27 03:15")
    }
}
