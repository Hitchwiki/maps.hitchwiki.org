package org.hitchwiki.maps.auth
import android.app.Activity
import androidx.browser.customtabs.CustomTabsIntent
import androidx.core.net.toUri
import kotlinx.coroutines.CompletableDeferred

/** Opens /api/auth/login in a Chrome Custom Tab and awaits the custom-scheme redirect.
 *  If the tab is dismissed, the host activity's onResume calls AuthRedirectBus.cancelIfDismissed()
 *  so this returns Cancelled instead of suspending forever. */
class AndroidAuthController(
    private val activity: Activity,
    private val baseUrl: String,
) : AuthController {
    override suspend fun signIn(): AuthResult {
        // Abandon any previous attempt so a dismissed tab can't leave a dangling deferred.
        AuthRedirectBus.deliver(AuthResult.Cancelled)
        val deferred = CompletableDeferred<AuthResult>()
        AuthRedirectBus.pending = deferred
        AuthRedirectBus.awaitingRedirect = true
        CustomTabsIntent.Builder().build().launchUrl(activity, "$baseUrl/api/auth/login".toUri())
        return deferred.await()
    }
}
