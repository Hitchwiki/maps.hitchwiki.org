package org.hitchwiki.maps.ui.account
import org.hitchwiki.maps.auth.AuthController
import org.hitchwiki.maps.auth.AuthResult
import org.hitchwiki.maps.data.*
import io.ktor.client.engine.mock.*
import io.ktor.client.request.*
import io.ktor.http.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.test.*
import kotlin.test.*

class AccountViewModelTest {
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

    @Test fun loadReflectsSignedInFromStoredToken() = runTest {
        val repo = AuthRepository(FakeController(AuthResult.Cancelled), FakeStore("T"),
            api { respond("""{"username":"bob"}""", HttpStatusCode.OK,
                headersOf(HttpHeaders.ContentType, "application/json")) })
        val vm = AccountViewModel(repo, this, StandardTestDispatcher(testScheduler))
        vm.load(); advanceUntilIdle()
        assertFalse(vm.state.value.loading)
        assertEquals(AuthStatus.SignedIn("bob"), vm.state.value.status)
    }

    @Test fun signInSuccessFlipsToSignedIn() = runTest {
        val repo = AuthRepository(FakeController(AuthResult.Success("c")), FakeStore(),
            api { respond("""{"token":"T","username":"alice"}""", HttpStatusCode.OK,
                headersOf(HttpHeaders.ContentType, "application/json")) })
        val vm = AccountViewModel(repo, this, StandardTestDispatcher(testScheduler))
        vm.signIn(); advanceUntilIdle()
        assertEquals(AuthStatus.SignedIn("alice"), vm.state.value.status)
        assertNull(vm.state.value.error)
    }

    @Test fun signInCancelledLeavesSignedOutNoError() = runTest {
        val repo = AuthRepository(FakeController(AuthResult.Cancelled), FakeStore(),
            api { respond("", HttpStatusCode.OK) })
        val vm = AccountViewModel(repo, this, StandardTestDispatcher(testScheduler))
        vm.signIn(); advanceUntilIdle()
        assertEquals(AuthStatus.SignedOut, vm.state.value.status)
        assertNull(vm.state.value.error)
        assertFalse(vm.state.value.loading)
    }

    @Test fun logoutFlipsToSignedOut() = runTest {
        val repo = AuthRepository(FakeController(AuthResult.Cancelled), FakeStore("T"),
            api { respond("""{"status":"ok"}""", HttpStatusCode.OK,
                headersOf(HttpHeaders.ContentType, "application/json")) })
        val vm = AccountViewModel(repo, this, StandardTestDispatcher(testScheduler))
        vm.logout(); advanceUntilIdle()
        assertEquals(AuthStatus.SignedOut, vm.state.value.status)
    }
}
