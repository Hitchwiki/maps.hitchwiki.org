package org.hitchwiki.maps.model
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class Spot(
    val lat: Double,
    val lon: Double,
    val rating: Double,
    @SerialName("review_count") val reviewCount: Int,
    @SerialName("latest_ms") val latestMs: Long? = null,
    @SerialName("dest_lats") val destLats: List<Double>? = null,
    @SerialName("dest_lons") val destLons: List<Double>? = null,
    // Presence flags: present-only-when-true in the JSON, so default false.
    val osm: Boolean = false,
    val cp: Boolean = false,
    val fuel: Boolean = false,
    val wiki: Boolean = false,
    val wikimap: Boolean = false,
)
