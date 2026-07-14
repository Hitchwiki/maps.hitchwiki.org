package org.hitchwiki.maps.data
import org.hitchwiki.maps.model.Spot
import io.ktor.client.engine.mock.*
import io.ktor.http.*
import kotlinx.coroutines.test.runTest
import kotlin.test.*

class SpotRepositoryTest {
    private class FakeCache(var stored: List<Spot> = emptyList()) : SpotCache {
        var saves = 0
        override suspend fun saveSpots(spots: List<Spot>) { stored = spots; saves++ }
        override suspend fun loadSpots(): List<Spot> = stored
    }
    private fun apiReturning(body: String) = HitchwikiApi(defaultHttpClient(MockEngine {
        respond(body, HttpStatusCode.OK, headersOf(HttpHeaders.ContentType, "application/json"))
    }), "https://example.test")
    private fun apiFailing() = HitchwikiApi(defaultHttpClient(MockEngine {
        respond("boom", HttpStatusCode.InternalServerError)
    }), "https://example.test")

    @Test fun networkSuccessPopulatesCache() = runTest {
        val cache = FakeCache()
        val repo = SpotRepository(apiReturning("""[{"lat":1.0,"lon":2.0,"rating":4.0,"review_count":3}]"""), cache)
        val spots = repo.spots()
        assertEquals(1, spots.size); assertEquals(1, cache.saves); assertEquals(1, cache.stored.size)
    }
    @Test fun networkFailureFallsBackToCache() = runTest {
        val cache = FakeCache(stored = listOf(Spot(lat = 9.0, lon = 9.0, rating = 5.0, reviewCount = 1)))
        val repo = SpotRepository(apiFailing(), cache)
        val spots = repo.spots()
        assertEquals(1, spots.size); assertEquals(9.0, spots[0].lat); assertEquals(0, cache.saves)
    }
    @Test fun bothFailPropagates() = runTest {
        val repo = SpotRepository(apiFailing(), FakeCache(stored = emptyList()))
        assertFailsWith<Throwable> { repo.spots() }
    }
}
