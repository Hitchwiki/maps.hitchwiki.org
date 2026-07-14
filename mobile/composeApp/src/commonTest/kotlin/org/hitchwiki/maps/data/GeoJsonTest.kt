package org.hitchwiki.maps.data
import org.hitchwiki.maps.model.Spot
import kotlinx.serialization.json.*
import kotlin.test.*

class GeoJsonTest {
    @Test fun emptyListIsEmptyFeatureCollection() {
        val fc = appJson.parseToJsonElement(buildSpotsGeoJson(emptyList())).jsonObject
        assertEquals("FeatureCollection", fc["type"]!!.jsonPrimitive.content)
        assertEquals(0, fc["features"]!!.jsonArray.size)
    }
    @Test fun oneSpotBecomesOneLonLatPointFeature() {
        val spots = listOf(Spot(lat = 51.0817, lon = 13.73629, rating = 5.0, reviewCount = 2))
        val fc = appJson.parseToJsonElement(buildSpotsGeoJson(spots)).jsonObject
        val feat = fc["features"]!!.jsonArray.single().jsonObject
        assertEquals("Feature", feat["type"]!!.jsonPrimitive.content)
        val coords = feat["geometry"]!!.jsonObject["coordinates"]!!.jsonArray
        // GeoJSON order is [lon, lat]
        assertEquals(13.73629, coords[0].jsonPrimitive.double)
        assertEquals(51.0817, coords[1].jsonPrimitive.double)
        val props = feat["properties"]!!.jsonObject
        assertEquals("51.08170_13.73629", props["sid"]!!.jsonPrimitive.content)
        assertEquals(5.0, props["rating"]!!.jsonPrimitive.double)
    }
    @Test fun featureCountMatchesInput() {
        val spots = List(3) { Spot(lat = it.toDouble(), lon = it.toDouble(), rating = 3.0, reviewCount = 1) }
        val fc = appJson.parseToJsonElement(buildSpotsGeoJson(spots)).jsonObject
        assertEquals(3, fc["features"]!!.jsonArray.size)
    }
}
