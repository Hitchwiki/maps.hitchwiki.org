package org.hitchwiki.maps.model
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class SpotDetail(val spot: SpotInfo = SpotInfo(), val rides: List<SpotRide> = emptyList())

/** An OSM element reference. car_pooling and fuel are emitted as {id, osm_type} objects (not
 *  strings) because these features are often tagged on ways/relations, not just nodes — both
 *  parts are needed to build a stable openstreetmap.org/{osm_type}/{id} URL. */
@Serializable
data class OsmRef(val id: Long, @SerialName("osm_type") val osmType: String)

// Click-time spot info slimmed out of spots.json; keys omitted when absent.
@Serializable
data class SpotInfo(
    val wait: Int? = null,
    val distance: Int? = null,
    @SerialName("osm_id") val osmId: Long? = null,
    @SerialName("car_pooling") val carPooling: OsmRef? = null,
    val fuel: OsmRef? = null,
    @SerialName("hitchwiki_article") val hitchwikiArticle: String? = null,
    @SerialName("hitchwiki_map") val hitchwikiMap: String? = null,
)

@Serializable
data class SpotRide(
    val id: String,
    val rating: Int? = null,
    val wait: Int? = null,
    val distance: Double? = null,
    val comment: String? = null,
    @SerialName("hitchhiker_name") val hitchhikerName: String = "Anonymous",
    @SerialName("submission_time") val submissionTime: String? = null,
    @SerialName("ride_datetime") val rideDatetime: String? = null,
    @SerialName("arrival_datetime") val arrivalDatetime: String? = null,
)
