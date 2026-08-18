package org.hitchwiki.maps.data
import org.hitchwiki.maps.model.Spot
import org.hitchwiki.maps.util.spotId

/** Build a GeoJSON FeatureCollection string for MapLibre's clustered GeoJsonSource.
 *  Each spot -> a Point at [lon, lat] (GeoJSON order) with `sid` (tap->detail lookup) and
 *  `rating` (color ramp). Built with a StringBuilder rather than the kotlinx JSON DSL because
 *  the DSL costs ~12 s for 35k features; direct appends are sub-second, which is what makes
 *  interactive filter rebuilds (and a faster cold load) viable. `sid` comes from spotId() and
 *  contains only [0-9 . _ -], so it needs no JSON string escaping. */
fun buildSpotsGeoJson(spots: List<Spot>): String {
    val sb = StringBuilder(spots.size * 96 + 48)
    sb.append("""{"type":"FeatureCollection","features":[""")
    for (i in spots.indices) {
        val s = spots[i]
        if (i > 0) sb.append(',')
        sb.append("""{"type":"Feature","geometry":{"type":"Point","coordinates":[""")
        sb.append(s.lon).append(',').append(s.lat)
        sb.append("""]},"properties":{"sid":"""").append(spotId(s.lat, s.lon))
        sb.append("""","rating":""").append(s.rating).append("}}")
    }
    sb.append("]}")
    return sb.toString()
}
