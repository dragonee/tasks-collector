import CryptoKit
import Foundation

/// Logging the phone in without the app ever seeing the password: OAuth 2.0
/// authorization code with PKCE (the server's side is `apps/common/oauth.py`).
///
/// 1. `start` makes up a verifier and a state, which the app keeps while the
///    browser is open.
/// 2. The browser opens `authorizeUrl`. The user logs in there as they do on
///    the web and says yes; the server sends the browser to `redirectUri`,
///    which is this app, with a code.
/// 3. `codeFrom` checks the answer is to the question asked, and the app
///    trades the code and the verifier for a token
///    (`TasksClient.exchangeCode`) that is its own and that the user can
///    revoke in their account settings.
enum OAuthLogin {

    /// How the server knows this app (`settings.OAUTH_CLIENTS`).
    static let clientId = "tasks-ios"

    /// A login the browser has been opened for.
    struct Pending: Equatable, Sendable {
        let serverUrl: String
        /// Random; its hash went out with the request, and only who has the
        /// verifier can use the code that comes back.
        let verifier: String
        /// Random; the answer has to carry it, or it answers another request.
        let state: String
    }

    /// What the browser came back with.
    enum Answer: Equatable {
        case code(String)
        case refused(String)
    }

    /// Where the server sends the browser when the user has answered: a URI
    /// of the app's own scheme, which is its bundle identifier (so a debug
    /// build, whose identifier ends in ".debug", gets its own answers).
    static func redirectUri(bundleId: String) -> String {
        "\(bundleId):/oauth"
    }

    static func start(serverUrl: String, random: () -> Data = randomBytes) -> Pending {
        Pending(
            serverUrl: TasksClient.trimmed(serverUrl),
            verifier: base64Url(random()),
            state: base64Url(random())
        )
    }

    /// The page to open in the browser, or nil when the server URL is no URL.
    static func authorizeUrl(_ pending: Pending, redirectUri: String, deviceName: String) -> URL? {
        guard var components = URLComponents(string: "\(pending.serverUrl)/oauth/authorize/"),
              let scheme = components.scheme, scheme == "http" || scheme == "https",
              components.host?.isEmpty == false
        else { return nil }
        components.queryItems = [
            URLQueryItem(name: "response_type", value: "code"),
            URLQueryItem(name: "client_id", value: clientId),
            URLQueryItem(name: "redirect_uri", value: redirectUri),
            URLQueryItem(name: "code_challenge", value: challenge(pending.verifier)),
            URLQueryItem(name: "code_challenge_method", value: "S256"),
            URLQueryItem(name: "state", value: pending.state),
            URLQueryItem(name: "device_name", value: deviceName),
        ]
        return components.url
    }

    /// The S256 challenge of a verifier: its SHA-256 in base64url, unpadded.
    static func challenge(_ verifier: String) -> String {
        base64Url(Data(SHA256.hash(data: Data(verifier.utf8))))
    }

    /// Read the answer the browser came back with: the `code`, `state` and
    /// `error` parameters of the redirect. `pending` is the login the app
    /// started, if any.
    static func codeFrom(_ pending: Pending?, code: String?, state: String?, error: String?) -> Answer {
        guard let pending else { return .refused("No login was started from this app.") }
        guard state == pending.state else { return .refused("That answer belongs to another login.") }
        if error == "access_denied" { return .refused("The login was cancelled.") }
        if let error { return .refused("The server refused the login (\(error)).") }
        guard let code, !code.isEmpty else { return .refused("The server sent no code.") }
        return .code(code)
    }

    /// The answer in the URL the browser was sent back to.
    static func codeFrom(_ pending: Pending?, callback: URL) -> Answer {
        let items = URLComponents(url: callback, resolvingAgainstBaseURL: false)?.queryItems ?? []
        func value(_ name: String) -> String? { items.first { $0.name == name }?.value }
        return codeFrom(pending, code: value("code"), state: value("state"), error: value("error"))
    }

    // 32 random bytes are 43 characters of base64url: the shortest verifier
    // the specification allows, and as long as its entropy needs.
    static func randomBytes() -> Data {
        var generator = SystemRandomNumberGenerator()
        return Data((0..<32).map { _ in UInt8.random(in: .min ... .max, using: &generator) })
    }

    private static func base64Url(_ bytes: Data) -> String {
        bytes.base64EncodedString()
            .replacingOccurrences(of: "+", with: "-")
            .replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: "=", with: "")
    }
}
