import Foundation
import Testing
@testable import TasksHealth

struct TripNoteFormatTests {

    private let utc = TimeZone.gmt

    // MARK: Where a note or photo was made

    private func decodeEvent(_ json: String) throws -> TripEvent {
        try JSONDecoder().decode(TripEvent.self, from: Data(json.utf8))
    }

    @Test func aNoteWithAPlaceHasItsLocationAndItsTextAsWritten() throws {
        let event = try decodeEvent(
            """
            {"id": 3, "type": "journal", "published": "2026-05-25T11:00:00Z",
             "comment": "Coffee at the corner\\n",
             "location": {"lat": 40.7128, "lng": -74.006, "acc": 12.5}}
            """
        )
        #expect(event.location == EventLocation(lat: 40.7128, lng: -74.006, acc: 12.5))
        #expect(event.comment == "Coffee at the corner\n")
    }

    @Test func aPlaceWithNoAccuracyIsStillAPlace() throws {
        let event = try decodeEvent(
            """
            {"id": 4, "type": "photo", "published": "2026-05-25T11:00:00Z", "comment": "",
             "thumbnail_url": null, "ready": false,
             "location": {"lat": -33.8688, "lng": 151.2093, "acc": null}}
            """
        )
        #expect(event.location == EventLocation(lat: -33.8688, lng: 151.2093))
    }

    @Test func anEventWithNoPlaceHasNoLocation() throws {
        let saidSo = try decodeEvent(
            """
            {"id": 5, "type": "journal", "published": "2026-05-25T11:00:00Z",
             "comment": "Plain note", "location": null}
            """
        )
        #expect(saidSo.location == nil)
        #expect(saidSo.comment == "Plain note")
        // A habit event, or a server from before locations: no key at all.
        let leftOut = try decodeEvent(
            """
            {"id": 6, "type": "habit", "published": "2026-05-25T11:00:00Z",
             "habit_slug": "walk", "habit_name": "Walk", "occured": true, "note": ""}
            """
        )
        #expect(leftOut.location == nil)
    }

    @Test func aLocationOpensInMapsWithAPinOnIt() {
        let url = EventLocation(lat: 52.229676, lng: 21.012229).mapsUrl
        #expect(url?.absoluteString == "https://maps.apple.com/?ll=52.229676,21.012229&q=52.229676,21.012229")
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
