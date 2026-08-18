package org.hitchwiki.maps.model
import org.hitchwiki.maps.util.spotId
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/** One record of spots_recent.json (latest ~1000 rides). `url` is a "#<lat>,<lon>" fragment. */
@Serializable
data class RecentRide(
    val url: String,
    @SerialName("submission_time") val submissionTime: String? = null,
    @SerialName("hitchhiker_name") val hitchhikerName: String? = null,
    val rating: Int? = null,
    val distance: Double? = null,
    val text: String? = null,
)

/** Parse "#lat,lon" -> (lat, lon); null if the url isn't exactly two parseable numbers. */
val RecentRide.latLon: Pair<Double, Double>?
    get() {
        val parts = url.removePrefix("#").split(",")
        if (parts.size != 2) return null
        val lat = parts[0].toDoubleOrNull() ?: return null
        val lon = parts[1].toDoubleOrNull() ?: return null
        return lat to lon
    }

val RecentRide.sid: String?
    get() = latLon?.let { spotId(it.first, it.second) }
