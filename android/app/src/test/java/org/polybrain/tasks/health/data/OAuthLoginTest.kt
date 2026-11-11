package org.polybrain.tasks.health.data

import okhttp3.HttpUrl.Companion.toHttpUrl
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class OAuthLoginTest {

    private val pending = OAuthLogin.Pending(
        serverUrl = "https://tasks.example.com",
        verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk",
        state = "the-state",
    )

    @Test
    fun `the challenge is the one the specification works out`() {
        // RFC 7636, appendix B.
        assertEquals(
            "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
            OAuthLogin.challenge(pending.verifier),
        )
    }

    @Test
    fun `a login starts with a verifier and a state nobody could guess`() {
        val one = OAuthLogin.start(" https://tasks.example.com/ ")
        val other = OAuthLogin.start("https://tasks.example.com")

        assertEquals("https://tasks.example.com", one.serverUrl)
        // What the server accepts as a verifier: 43 to 128 unreserved characters.
        assertTrue(Regex("[A-Za-z0-9_-]{43}").matches(one.verifier))
        assertNotEquals(one.verifier, one.state)
        assertNotEquals(one.verifier, other.verifier)
        assertNotEquals(one.state, other.state)
    }

    @Test
    fun `the page asks for a code for this app, sent back to this app`() {
        val url = OAuthLogin.authorizeUrl(
            pending,
            OAuthLogin.redirectUri("org.polybrain.tasks.health.debug"),
            "Google Pixel 8",
        )!!.toHttpUrl()

        assertEquals("https://tasks.example.com/oauth/authorize/", url.newBuilder().query(null).build().toString())
        assertEquals("code", url.queryParameter("response_type"))
        assertEquals("tasks-android", url.queryParameter("client_id"))
        assertEquals("org.polybrain.tasks.health.debug:/oauth", url.queryParameter("redirect_uri"))
        assertEquals("S256", url.queryParameter("code_challenge_method"))
        assertEquals(OAuthLogin.challenge(pending.verifier), url.queryParameter("code_challenge"))
        assertEquals("the-state", url.queryParameter("state"))
        assertEquals("Google Pixel 8", url.queryParameter("device_name"))
        // The verifier stays on the phone.
        assertTrue(pending.verifier !in url.toString())
    }

    @Test
    fun `a server under a path keeps its path`() {
        val url = OAuthLogin.authorizeUrl(
            OAuthLogin.start("http://10.0.2.2:8000/tasks/"), "app:/oauth", "",
        )!!

        assertTrue(url.startsWith("http://10.0.2.2:8000/tasks/oauth/authorize/?"))
    }

    @Test
    fun `what is no URL opens no page`() {
        assertNull(OAuthLogin.authorizeUrl(OAuthLogin.start("tasks example"), "app:/oauth", ""))
        assertNull(OAuthLogin.authorizeUrl(OAuthLogin.start(""), "app:/oauth", ""))
    }

    @Test
    fun `the answer to the login that was started gives its code`() {
        assertEquals(
            OAuthLogin.Answer.Code("c0de"),
            OAuthLogin.codeFrom(pending, code = "c0de", state = "the-state", error = null),
        )
    }

    @Test
    fun `any other answer gives none`() {
        fun refused(pending: OAuthLogin.Pending?, code: String?, state: String?, error: String?) =
            assertTrue(OAuthLogin.codeFrom(pending, code, state, error) is OAuthLogin.Answer.Refused)

        // Nothing was asked.
        refused(null, "c0de", "the-state", null)
        // An answer to something else: another login, or someone's own link.
        refused(pending, "c0de", "another-state", null)
        refused(pending, "c0de", null, null)
        // The user said no, or the server did.
        refused(pending, null, "the-state", "access_denied")
        refused(pending, "c0de", "the-state", "invalid_request")
        refused(pending, null, "the-state", null)
        refused(pending, "", "the-state", null)
    }
}
