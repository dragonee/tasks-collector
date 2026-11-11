import Testing
@testable import TasksHealth

struct PhotoLocationResolverTests {

    private let minute: Int64 = 60_000

    @Test func emptyTrailYieldsNoLocation() {
        #expect(PhotoLocationResolver.resolve([], captureMs: 1_000) == nil)
    }

    @Test func directHitWithinTwoMinutesUsesTheNearestPoint() {
        let crumbs = [
            Breadcrumb(t: 0, lat: 10, lng: 10),
            Breadcrumb(t: 1 * minute, lat: 20, lng: 20),
            Breadcrumb(t: 5 * minute, lat: 50, lng: 50),
        ]
        let fix = PhotoLocationResolver.resolve(crumbs, captureMs: 2 * minute)
        // The point at 1 min is a minute away, the one at 5 min three.
        #expect(fix?.lat == 20)
        #expect(fix?.lng == 20)
    }

    @Test func gapBracketedByNearbyPointsUsesTheCloserOneInTime() {
        // No point within 2 min of the capture, but the ones before and after
        // are about 110 m apart: the same place, so the closer in time is used.
        let crumbs = [
            Breadcrumb(t: 0, lat: 52.230000, lng: 21.010000),
            Breadcrumb(t: 13 * minute, lat: 52.231000, lng: 21.010000),
        ]
        let fix = PhotoLocationResolver.resolve(crumbs, captureMs: 10 * minute)
        // 3 min after is closer than 10 min before.
        #expect(fix?.lat == 52.231000)
    }

    @Test func gapBracketedByFarApartPointsYieldsNoLocation() {
        // About 19 km between the two: the user was moving, so no guess.
        let crumbs = [
            Breadcrumb(t: 0, lat: 52.2300, lng: 21.0100),
            Breadcrumb(t: 20 * minute, lat: 52.4000, lng: 21.0100),
        ]
        #expect(PhotoLocationResolver.resolve(crumbs, captureMs: 10 * minute) == nil)
    }

    @Test func onlyOneSideInAGapYieldsNoLocation() {
        // Taken well after the last breadcrumb (tracking had ended): there is
        // no pair around it to say the user stayed put.
        let crumbs = [
            Breadcrumb(t: 0, lat: 10, lng: 10),
            Breadcrumb(t: 5 * minute, lat: 10, lng: 10),
        ]
        #expect(PhotoLocationResolver.resolve(crumbs, captureMs: 30 * minute) == nil)
    }

    @Test func exactTimestampMatchIsADirectHit() {
        let crumbs = [Breadcrumb(t: 7 * minute, lat: 1, lng: 2, acc: 9)]
        let fix = PhotoLocationResolver.resolve(crumbs, captureMs: 7 * minute)
        #expect(fix?.lat == 1)
        #expect(fix?.accuracyMeters == 9)
    }

    @Test func haversineMatchesAKnownCityScaleDistance() {
        // From the centre of Warsaw to about 1 km north (0.009° of latitude).
        let d = PhotoLocationResolver.haversineMeters(52.2297, 21.0122, 52.2387, 21.0122)
        #expect(abs(d - 1000) <= 5)
    }
}
