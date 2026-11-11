package org.polybrain.tasks.health.data

import java.security.MessageDigest
import java.security.SecureRandom
import java.util.Base64
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull

/**
 * Logging the phone in without the app ever seeing the password: OAuth 2.0
 * authorization code with PKCE (the server's side is `apps/common/oauth.py`).
 *
 * 1. [start] makes up a verifier and a state and the app keeps them
 *    ([Settings.savePendingLogin]) while the browser is open.
 * 2. The browser opens [authorizeUrl]. The user logs in there as they do on
 *    the web and says yes; the server sends the browser to [redirectUri],
 *    which is this app, with a code.
 * 3. [codeFrom] checks the answer is to the question asked, and the app
 *    trades the code and the verifier for a token ([TasksClient.exchangeCode])
 *    that is its own and that the user can revoke in their account settings.
 */
object OAuthLogin {

    /** How the server knows this app (`settings.OAUTH_CLIENTS`). */
    const val CLIENT_ID = "tasks-android"

    /** A login the browser has been opened for. */
    data class Pending(
        val serverUrl: String,
        // Random; its hash went out with the request, and only who has the
        // verifier can use the code that comes back.
        val verifier: String,
        // Random; the answer has to carry it, or it answers another request.
        val state: String,
    )

    /** What the browser came back with. */
    sealed class Answer {
        data class Code(val code: String) : Answer()
        data class Refused(val reason: String) : Answer()
    }

    /**
     * Where the server sends the browser when the user has answered: a URI
     * of the app's own scheme, which is its package name (so a debug build,
     * whose package ends in ".debug", gets its own answers).
     */
    fun redirectUri(applicationId: String): String = "$applicationId:/oauth"

    fun start(serverUrl: String, random: SecureRandom = SecureRandom()): Pending =
        Pending(
            serverUrl = serverUrl.trim().trimEnd('/'),
            verifier = randomToken(random),
            state = randomToken(random),
        )

    /** The page to open in the browser, or null when the server URL is no URL. */
    fun authorizeUrl(pending: Pending, redirectUri: String, deviceName: String): String? =
        "${pending.serverUrl}/oauth/authorize/".toHttpUrlOrNull()
            ?.newBuilder()
            ?.addQueryParameter("response_type", "code")
            ?.addQueryParameter("client_id", CLIENT_ID)
            ?.addQueryParameter("redirect_uri", redirectUri)
            ?.addQueryParameter("code_challenge", challenge(pending.verifier))
            ?.addQueryParameter("code_challenge_method", "S256")
            ?.addQueryParameter("state", pending.state)
            ?.addQueryParameter("device_name", deviceName)
            ?.build()
            ?.toString()

    /** The S256 challenge of a verifier: its SHA-256 in base64url, unpadded. */
    fun challenge(verifier: String): String =
        base64Url(MessageDigest.getInstance("SHA-256").digest(verifier.toByteArray(Charsets.US_ASCII)))

    /**
     * Read the answer the browser came back with: the `code`, `state` and
     * `error` parameters of the redirect. [pending] is the login the app
     * started, if any.
     */
    fun codeFrom(pending: Pending?, code: String?, state: String?, error: String?): Answer =
        when {
            pending == null -> Answer.Refused("No login was started from this app.")
            state != pending.state -> Answer.Refused("That answer belongs to another login.")
            error == "access_denied" -> Answer.Refused("The login was cancelled.")
            error != null -> Answer.Refused("The server refused the login ($error).")
            code.isNullOrEmpty() -> Answer.Refused("The server sent no code.")
            else -> Answer.Code(code)
        }

    // 32 random bytes are 43 characters of base64url: the shortest verifier
    // the specification allows, and as long as its entropy needs.
    private fun randomToken(random: SecureRandom): String =
        base64Url(ByteArray(32).also(random::nextBytes))

    private fun base64Url(bytes: ByteArray): String =
        Base64.getUrlEncoder().withoutPadding().encodeToString(bytes)
}
