package org.hitchwiki.maps.data
import io.ktor.client.engine.mock.*
import io.ktor.http.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.test.*
import kotlin.test.*

class RecentRidesSourceTest {
    @Test fun fetchesAndParsesSpotsRecent() = runTest {
        val body = """[{"url":"#1.0,2.0","hitchhiker_name":"alice","rating":5,"text":"good"},
                       {"url":"#3.0,4.0","hitchhiker_name":"bob","rating":3,"text":"ok"}]"""
        val api = HitchwikiApi(defaultHttpClient(MockEngine(MockEngineConfig().apply {
            addHandler { req ->
                assertTrue(req.url.encodedPath.endsWith("/spots_recent.json"))
                respond(body, HttpStatusCode.OK, headersOf(HttpHeaders.ContentType, "application/json"))
            }
            dispatcher = Dispatchers.Unconfined
        })), "https://example.test")
        val out = ApiRecentRidesSource(api).recent()
        assertEquals(2, out.size)
        assertEquals("alice", out[0].hitchhikerName)
    }
}
