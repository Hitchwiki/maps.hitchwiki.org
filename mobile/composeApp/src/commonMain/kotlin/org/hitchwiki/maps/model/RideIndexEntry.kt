package org.hitchwiki.maps.model
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

// rides_index.json uses short keys to keep the file small; map them to readable names.
@Serializable
data class RideIndexEntry(
    val id: String,
    val sid: String,
    val lat: Double,
    val lon: Double,
    @SerialName("u") val user: String,
    @SerialName("t") val submittedMs: Long? = null,
    @SerialName("r") val rating: Int? = null,
    @SerialName("km") val distanceKm: Double? = null,
    @SerialName("w") val waitMin: Int? = null,
    val osm: Boolean = false,
    val wiki: Boolean = false,
    val cp: Boolean = false,
    val fuel: Boolean = false,
    @SerialName("v") val vehicleKind: String? = null,
    @SerialName("m") val signalMethods: List<String>? = null,
    @SerialName("rd") val rideDatetimeMs: Long? = null,
    @SerialName("c") val comment: String? = null,
)
