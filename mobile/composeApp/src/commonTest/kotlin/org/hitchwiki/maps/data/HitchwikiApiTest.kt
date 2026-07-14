package org.hitchwiki.maps.data
import io.ktor.client.engine.mock.*
import io.ktor.http.*
import io.ktor.utils.io.*
import kotlinx.coroutines.test.runTest
import kotlin.test.*

class HitchwikiApiTest {
    private fun api(handler: MockRequestHandler): HitchwikiApi {
        val engine = MockEngine(handler)
        return HitchwikiApi(defaultHttpClient(engine), baseUrl = "https://example.test")
    }
    // respond() is an extension on MockRequestHandleScope (Ktor 3.0.1), so ok() must be one too
    // to pick up the implicit receiver from the handler lambda.
    private fun MockRequestHandleScope.ok(body: String) = respond(body, HttpStatusCode.OK,
        headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()))

    @Test fun spotsHitsSpotsJson() = runTest {
        var path: String? = null
        val a = api { req -> path = req.url.encodedPath; ok("""[{"lat":1.0,"lon":2.0,"rating":4.0,"review_count":3}]""") }
        val spots = a.spots()
        assertEquals("/spots.json", path)
        assertEquals(1, spots.size); assertEquals(3, spots[0].reviewCount)
    }
    @Test fun spotDetailUsesSidPath() = runTest {
        var path: String? = null
        val a = api { req -> path = req.url.encodedPath; ok("""{"spot":{"wait":5},"rides":[]}""") }
        val d = a.spotDetail("38.65081_68.76809")
        assertEquals("/rides/by-spot/38.65081_68.76809.json", path)
        assertEquals(5, d.spot.wait)
    }
    @Test fun ridesIndexHitsRidesIndexJson() = runTest {
        var path: String? = null
        val a = api { req -> path = req.url.encodedPath; ok(
            """[{"id":"src-xyz","sid":"48.13743_11.57549","lat":48.13743,"lon":11.57549,
                "u":"bob","t":1735548300000,"r":4,"km":42.5,"w":15,"osm":true,"wiki":true,"cp":false,
                "v":"car","m":["thumb","sign"],"rd":1735548300000,"fuel":true,"c":"nice"}]""") }
        val rides = a.ridesIndex()
        assertEquals("/rides_index.json", path)
        assertEquals(1, rides.size)
        assertEquals("src-xyz", rides[0].id)
        assertEquals(1735548300000L, rides[0].rideDatetimeMs)
    }
}
