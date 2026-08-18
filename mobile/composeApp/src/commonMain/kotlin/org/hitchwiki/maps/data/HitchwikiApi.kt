package org.hitchwiki.maps.data
import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.engine.HttpClientEngine
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.client.request.get
import io.ktor.client.request.header
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.contentType
import io.ktor.serialization.kotlinx.json.json
import org.hitchwiki.maps.model.MeResponse
import org.hitchwiki.maps.model.RecentRide
import org.hitchwiki.maps.model.RideIndexEntry
import org.hitchwiki.maps.model.Spot
import org.hitchwiki.maps.model.SpotDetail
import org.hitchwiki.maps.model.TokenRequest
import org.hitchwiki.maps.model.TokenResponse

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
    suspend fun recentRides(): List<RecentRide> = client.get("$baseUrl/spots_recent.json").body()

    suspend fun authToken(code: String): TokenResponse =
        client.post("$baseUrl/api/auth/token") {
            contentType(ContentType.Application.Json)
            setBody(TokenRequest(code))
        }.body()

    suspend fun authMe(token: String): MeResponse =
        client.get("$baseUrl/api/auth/me") {
            header(HttpHeaders.Authorization, "Bearer $token")
        }.body()

    suspend fun authLogout(token: String) {
        client.post("$baseUrl/api/auth/logout") {
            header(HttpHeaders.Authorization, "Bearer $token")
        }
    }

    companion object { const val BASE_URL = "https://maps.hitchwiki.org" }
}
