package org.hitchwiki.maps.data
import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.engine.HttpClientEngine
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.client.request.get
import io.ktor.serialization.kotlinx.json.json
import org.hitchwiki.maps.model.RideIndexEntry
import org.hitchwiki.maps.model.Spot
import org.hitchwiki.maps.model.SpotDetail

fun defaultHttpClient(engine: HttpClientEngine): HttpClient =
    HttpClient(engine) {
        // Non-2xx responses throw, so the repository's offline fallback fires on server
        // errors even when the error body would otherwise parse as valid JSON.
        expectSuccess = true
        install(ContentNegotiation) { json(appJson) }
    }

class HitchwikiApi(private val client: HttpClient, private val baseUrl: String = BASE_URL) {
    suspend fun spots(): List<Spot> = client.get("$baseUrl/spots.json").body()
    suspend fun ridesIndex(): List<RideIndexEntry> = client.get("$baseUrl/rides_index.json").body()
    // Per-spot detail filename is the spot id; see util.spotId / generate_spot_id.
    suspend fun spotDetail(sid: String): SpotDetail = client.get("$baseUrl/rides/by-spot/$sid.json").body()
    companion object { const val BASE_URL = "https://maps.hitchwiki.org" }
}
