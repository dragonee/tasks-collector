import Foundation
import Testing
@testable import TasksHealth

struct OAuthLoginTests {

    private let pending = OAuthLogin.Pending(
        serverUrl: "https://tasks.example.com",
        verifier: "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk",
        state: "the-state"
    )

    @Test func theChallengeIsTheOneTheSpecificationWorksOut() {
        // RFC 7636, appendix B.
        #expect(OAuthLogin.challenge(pending.verifier) == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM")
    }

    @Test func aLoginStartsWithAVerifierAndAStateNobodyCouldGuess() {
        let one = OAuthLogin.start(serverUrl: " https://tasks.example.com/ ")
        let other = OAuthLogin.start(serverUrl: "https://tasks.example.com")

        #expect(one.serverUrl == "https://tasks.example.com")
        // What the server accepts as a verifier: 43 to 128 unreserved characters.
        #expect(one.verifier.wholeMatch(of: #/[A-Za-z0-9_-]{43}/#) != nil)
        #expect(one.verifier != one.state)
        #expect(one.verifier != other.verifier)
        #expect(one.state != other.state)
    }

    @Test func thePageAsksForACodeForThisAppSentBackToThisApp() throws {
        let url = try #require(
            OAuthLogin.authorizeUrl(
                pending,
                redirectUri: OAuthLogin.redirectUri(bundleId: "org.polybrain.tasks.health.debug"),
                deviceName: "iPhone 17 Pro"
            )
        )
        var components = try #require(URLComponents(url: url, resolvingAgainstBaseURL: false))
        let items = components.queryItems ?? []
        func parameter(_ name: String) -> String? { items.first { $0.name == name }?.value }

        components.query = nil
        #expect(components.string == "https://tasks.example.com/oauth/authorize/")
        #expect(parameter("response_type") == "code")
        #expect(parameter("client_id") == "tasks-ios")
        #expect(parameter("redirect_uri") == "org.polybrain.tasks.health.debug:/oauth")
        #expect(parameter("code_challenge_method") == "S256")
        #expect(parameter("code_challenge") == OAuthLogin.challenge(pending.verifier))
        #expect(parameter("state") == "the-state")
        #expect(parameter("device_name") == "iPhone 17 Pro")
        // The verifier stays on the phone.
        #expect(!url.absoluteString.contains(pending.verifier))
    }

    @Test func aServerUnderAPathKeepsItsPath() throws {
        let url = try #require(
            OAuthLogin.authorizeUrl(
                OAuthLogin.start(serverUrl: "http://localhost:8000/tasks/"),
                redirectUri: "app:/oauth",
                deviceName: ""
            )
        )

        #expect(url.absoluteString.hasPrefix("http://localhost:8000/tasks/oauth/authorize/?"))
    }

    @Test func whatIsNoUrlOpensNoPage() {
        #expect(
            OAuthLogin.authorizeUrl(
                OAuthLogin.start(serverUrl: "tasks example"), redirectUri: "app:/oauth", deviceName: ""
            ) == nil
        )
        #expect(
            OAuthLogin.authorizeUrl(
                OAuthLogin.start(serverUrl: ""), redirectUri: "app:/oauth", deviceName: ""
            ) == nil
        )
    }

    @Test func theAnswerToTheLoginThatWasStartedGivesItsCode() {
        #expect(OAuthLogin.codeFrom(pending, code: "c0de", state: "the-state", error: nil) == .code("c0de"))
    }

    @Test func anyOtherAnswerGivesNone() {
        func refused(_ pending: OAuthLogin.Pending?, _ code: String?, _ state: String?, _ error: String?) -> Bool {
            if case .refused = OAuthLogin.codeFrom(pending, code: code, state: state, error: error) { true } else { false }
        }

        // Nothing was asked.
        #expect(refused(nil, "c0de", "the-state", nil))
        // An answer to something else: another login, or someone's own link.
        #expect(refused(pending, "c0de", "another-state", nil))
        #expect(refused(pending, "c0de", nil, nil))
        // The user said no, or the server did.
        #expect(refused(pending, nil, "the-state", "access_denied"))
        #expect(refused(pending, "c0de", "the-state", "invalid_request"))
        #expect(refused(pending, nil, "the-state", nil))
        #expect(refused(pending, "", "the-state", nil))
    }
}
