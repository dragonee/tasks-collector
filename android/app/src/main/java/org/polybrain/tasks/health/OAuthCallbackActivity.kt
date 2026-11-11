package org.polybrain.tasks.health

import android.app.Activity
import android.content.Intent
import android.os.Bundle

/**
 * Where the browser lands when the user has answered the login page: the
 * server redirects it to a URI of this app's own scheme (see
 * `data/OAuthLogin.kt`), which the manifest gives to this activity.
 *
 * It shows nothing. It hands the URI to [MainActivity] — the one already
 * running, brought back in front of the browser, or a new one when Android
 * has killed the app meanwhile — and is gone.
 */
class OAuthCallbackActivity : Activity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        startActivity(
            Intent(this, MainActivity::class.java)
                .setData(intent.data)
                .addFlags(
                    Intent.FLAG_ACTIVITY_NEW_TASK or
                        Intent.FLAG_ACTIVITY_CLEAR_TOP or
                        Intent.FLAG_ACTIVITY_SINGLE_TOP,
                )
        )
        finish()
    }
}
