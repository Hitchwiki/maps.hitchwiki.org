package org.hitchwiki.maps.data
import org.hitchwiki.maps.model.Spot
import org.hitchwiki.maps.util.spotId
import kotlinx.serialization.json.*

/** Build a GeoJSON FeatureCollection string for MapLibre's clustered GeoJsonSource.
 *  Each spot → a Point at [lon, lat] (GeoJSON order) with `sid` (for the tap→detail lookup)
 *  and `rating` (for the color ramp). Returned as a String so no MapLibre type leaks into
 *  commonMain — the Android actual feeds the String straight into GeoJsonSource. */
fun buildSpotsGeoJson(spots: List<Spot>): String {
    val features = spots.map { s ->
        buildJsonObject {
            put("type", "Feature")
            putJsonObject("geometry") {
                put("type", "Point")
                putJsonArray("coordinates") { add(s.lon); add(s.lat) }
            }
            putJsonObject("properties") {
                put("sid", spotId(s.lat, s.lon))
                put("rating", s.rating)
            }
        }
    }
    val fc = buildJsonObject {
        put("type", "FeatureCollection")
        put("features", JsonArray(features))
    }
    return fc.toString()
}
