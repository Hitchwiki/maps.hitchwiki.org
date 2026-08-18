package org.hitchwiki.maps.data
import io.ktor.client.engine.mock.*
import io.ktor.client.request.*
import io.ktor.http.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.test.*
import kotlin.test.*

class HitchwikiApiAuthTest {
    private fun api(handler: MockRequestHandleScope.(io.ktor.client.request.HttpRequestData) -> HttpResponseData) =
        HitchwikiApi(defaultHttpClient(MockEngine(MockEngineConfig().apply {
            addHandler(handler); dispatcher = Dispatchers.Unconfined
        })), "https://example.test")

    @Test fun authTokenPostsCodeAndParsesResponse() = runTest {
        val a = api { req ->
            assertTrue(req.url.encodedPath.endsWith("/api/auth/token"))
            assertEquals(HttpMethod.Post, req.method)
            respond("""{"token":"tok123","username":"alice"}""", HttpStatusCode.OK,
                headersOf(HttpHeaders.ContentType, "application/json"))
        }
        val out = a.authToken("code-abc")
        assertEquals("tok123", out.token)
        assertEquals("alice", out.username)
    }

    @Test fun authMeSendsBearerAndParsesUsername() = runTest {
        val a = api { req ->
            assertTrue(req.url.encodedPath.endsWith("/api/auth/me"))
            assertEquals("Bearer tok123", req.headers[HttpHeaders.Authorization])
            respond("""{"username":"bob"}""", HttpStatusCode.OK,
                headersOf(HttpHeaders.ContentType, "application/json"))
        }
        assertEquals("bob", a.authMe("tok123").username)
    }

    @Test fun authLogoutSendsBearer() = runTest {
        var seen: String? = null
        val a = api { req ->
            seen = req.headers[HttpHeaders.Authorization]
            respond("""{"status":"ok"}""", HttpStatusCode.OK,
                headersOf(HttpHeaders.ContentType, "application/json"))
        }
        a.authLogout("tok123")
        assertEquals("Bearer tok123", seen)
    }
}
