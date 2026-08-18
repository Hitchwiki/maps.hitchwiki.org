package org.hitchwiki.maps.auth
import android.app.Activity
import android.os.Bundle
import kotlinx.coroutines.CompletableDeferred

/** Process-level rendezvous between the Custom Tab redirect and the suspended signIn(). */
object AuthRedirectBus {
    // Set by AndroidAuthController before opening the tab; completed by OAuthRedirectActivity.
    @Volatile var pending: CompletableDeferred<AuthResult>? = null

    fun deliver(result: AuthResult) {
        pending?.complete(result)
        pending = null
    }

    /** True once the tab has actually been opened, so the first resume after launching is the
     *  browser leg starting rather than the user returning. Without this, MainActivity's own
     *  onResume (which fires right after launchUrl on some devices) would cancel immediately. */
    @Volatile var awaitingRedirect: Boolean = false

    /** Called when the host activity regains focus. If a sign-in is still pending at that point
     *  the Custom Tab was dismissed without a redirect, so the suspended signIn() would otherwise
     *  hang forever and leave the Account screen stuck in `loading`. */
    fun cancelIfDismissed() {
        if (!awaitingRedirect) return
        awaitingRedirect = false
        deliver(AuthResult.Cancelled)
    }
}

/** Captures hitchwiki-app://oauth-callback?code=… , hands the code to the bus, finishes. */
class OAuthRedirectActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val code = intent?.data?.getQueryParameter("code")
        // The redirect arrived, so the host activity's next resume must not cancel this attempt.
        AuthRedirectBus.awaitingRedirect = false
        AuthRedirectBus.deliver(
            if (code != null) AuthResult.Success(code) else AuthResult.Error("No code in redirect"),
        )
        finish()
    }
}
