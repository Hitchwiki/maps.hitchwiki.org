package org.hitchwiki.maps.data
import org.hitchwiki.maps.auth.AuthController
import org.hitchwiki.maps.auth.AuthResult
import io.ktor.client.plugins.ClientRequestException
import io.ktor.http.HttpStatusCode

/** Logged-in identity as far as the app can tell right now. */
sealed interface AuthStatus {
    data class SignedIn(val username: String) : AuthStatus
    data object SignedOut : AuthStatus
    data object Unknown : AuthStatus     // couldn't verify (offline / server error); keep the token
}

/** Result of an interactive sign-in attempt. */
sealed interface SignInOutcome {
    data class Success(val username: String) : SignInOutcome
    data object Cancelled : SignInOutcome
    data class Failed(val message: String) : SignInOutcome
}

/** Orchestrates auth over the three seams. Pure logic — no platform types. */
class AuthRepository(
    private val controller: AuthController,
    private val store: TokenStore,
    private val api: HitchwikiApi,
) {
    suspend fun signIn(): SignInOutcome =
        when (val r = controller.signIn()) {
            is AuthResult.Cancelled -> SignInOutcome.Cancelled
            is AuthResult.Error -> SignInOutcome.Failed(r.message)
            is AuthResult.Success -> try {
                val resp = api.authToken(r.code)
                store.save(resp.token)
                SignInOutcome.Success(resp.username)
            } catch (e: Throwable) {
                SignInOutcome.Failed(e.message ?: "Sign-in failed")
            }
        }

    /** Validate the stored token. 401 => clear + signed out; other errors => keep token, Unknown. */
    suspend fun currentUser(): AuthStatus {
        val token = store.load() ?: return AuthStatus.SignedOut
        return try {
            AuthStatus.SignedIn(api.authMe(token).username)
        } catch (e: ClientRequestException) {
            if (e.response.status == HttpStatusCode.Unauthorized) {
                store.clear()
                AuthStatus.SignedOut
            } else {
                AuthStatus.Unknown
            }
        } catch (e: Throwable) {
            AuthStatus.Unknown
        }
    }

    /** Best-effort server revoke, then always clear locally. */
    suspend fun logout() {
        val token = store.load()
        if (token != null) {
            try { api.authLogout(token) } catch (_: Throwable) { }
        }
        store.clear()
    }
}
