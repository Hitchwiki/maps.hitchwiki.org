package org.hitchwiki.maps.data
import org.hitchwiki.maps.auth.AuthController
import org.hitchwiki.maps.auth.AuthResult
import io.ktor.client.engine.mock.*
import io.ktor.client.request.*
import io.ktor.http.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.test.*
import kotlin.test.*

class AuthRepositoryTest {
    private class FakeStore(var token: String? = null) : TokenStore {
        override suspend fun save(token: String) { this.token = token }
        override suspend fun load(): String? = token
        override suspend fun clear() { token = null }
    }
    private class FakeController(val result: AuthResult) : AuthController {
        override suspend fun signIn(): AuthResult = result
    }
    private fun api(handler: MockRequestHandleScope.(io.ktor.client.request.HttpRequestData) -> HttpResponseData) =
        HitchwikiApi(defaultHttpClient(MockEngine(MockEngineConfig().apply {
            addHandler(handler); dispatcher = Dispatchers.Unconfined
        })), "https://example.test")

    @Test fun signInSuccessStoresTokenAndReturnsUsername() = runTest {
        val store = FakeStore()
        val repo = AuthRepository(FakeController(AuthResult.Success("code1")), store,
            api { respond("""{"token":"T","username":"alice"}""", HttpStatusCode.OK,
                headersOf(HttpHeaders.ContentType, "application/json")) })
        val out = repo.signIn()
        assertEquals(SignInOutcome.Success("alice"), out)
        assertEquals("T", store.token)
    }

    @Test fun signInCancelledStoresNothing() = runTest {
        val store = FakeStore()
        val repo = AuthRepository(FakeController(AuthResult.Cancelled), store,
            api { respond("", HttpStatusCode.OK) })
        assertEquals(SignInOutcome.Cancelled, repo.signIn())
        assertNull(store.token)
    }

    @Test fun currentUserSignedInWhenTokenValid() = runTest {
        val repo = AuthRepository(FakeController(AuthResult.Cancelled), FakeStore("T"),
            api { respond("""{"username":"bob"}""", HttpStatusCode.OK,
                headersOf(HttpHeaders.ContentType, "application/json")) })
        assertEquals(AuthStatus.SignedIn("bob"), repo.currentUser())
    }

    @Test fun currentUserSignedOutWhenNoToken() = runTest {
        val repo = AuthRepository(FakeController(AuthResult.Cancelled), FakeStore(null),
            api { respond("", HttpStatusCode.OK) })
        assertEquals(AuthStatus.SignedOut, repo.currentUser())
    }

    @Test fun currentUser401ClearsTokenAndSignsOut() = runTest {
        val store = FakeStore("bad")
        val repo = AuthRepository(FakeController(AuthResult.Cancelled), store,
            api { respond("""{"error":"unauthorized"}""", HttpStatusCode.Unauthorized,
                headersOf(HttpHeaders.ContentType, "application/json")) })
        assertEquals(AuthStatus.SignedOut, repo.currentUser())
        assertNull(store.token)
    }

    @Test fun currentUserNetworkErrorKeepsTokenAndReturnsUnknown() = runTest {
        val store = FakeStore("T")
        val repo = AuthRepository(FakeController(AuthResult.Cancelled), store,
            api { respond("boom", HttpStatusCode.InternalServerError) })
        assertEquals(AuthStatus.Unknown, repo.currentUser())
        assertEquals("T", store.token)   // offline/5xx must NOT log the user out
    }

    @Test fun logoutClearsTokenLocally() = runTest {
        val store = FakeStore("T")
        val repo = AuthRepository(FakeController(AuthResult.Cancelled), store,
            api { respond("""{"status":"ok"}""", HttpStatusCode.OK,
                headersOf(HttpHeaders.ContentType, "application/json")) })
        repo.logout()
        assertNull(store.token)
    }
}
