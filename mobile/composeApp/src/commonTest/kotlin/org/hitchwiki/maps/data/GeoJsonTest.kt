package org.hitchwiki.maps.data
import org.hitchwiki.maps.model.Spot
import kotlinx.serialization.json.*
import kotlin.test.*

class GeoJsonTest {
    private fun spot(lat: Double, lon: Double, rating: Double) =
        Spot(lat = lat, lon = lon, rating = rating, reviewCount = 1)

    @Test fun emptyListIsEmptyCollection() {
        assertEquals("""{"type":"FeatureCollection","features":[]}""", buildSpotsGeoJson(emptyList()))
    }

    @Test fun buildsPointFeatureWithSidAndRating() {
        val json = appJson.parseToJsonElement(buildSpotsGeoJson(listOf(spot(51.0817, 13.73629, 4.0)))).jsonObject
        assertEquals("FeatureCollection", json["type"]!!.jsonPrimitive.content)
        val feats = json["features"]!!.jsonArray
        assertEquals(1, feats.size)
        val f = feats[0].jsonObject
        assertEquals("Feature", f["type"]!!.jsonPrimitive.content)
        val coords = f["geometry"]!!.jsonObject["coordinates"]!!.jsonArray
        assertEquals(13.73629, coords[0].jsonPrimitive.double)   // lon first (GeoJSON order)
        assertEquals(51.0817, coords[1].jsonPrimitive.double)
        val props = f["properties"]!!.jsonObject
        assertEquals("51.08170_13.73629", props["sid"]!!.jsonPrimitive.content)
        assertEquals(4.0, props["rating"]!!.jsonPrimitive.double)
    }

    @Test fun featureCountMatchesInputAndIsValidJson() {
        val spots = listOf(spot(1.0, 2.0, 5.0), spot(3.0, 4.0, 3.0), spot(-5.5, 6.25, 1.0))
        val feats = appJson.parseToJsonElement(buildSpotsGeoJson(spots)).jsonObject["features"]!!.jsonArray
        assertEquals(3, feats.size)
        // negative + fractional coordinates round-trip
        val third = feats[2].jsonObject["geometry"]!!.jsonObject["coordinates"]!!.jsonArray
        assertEquals(6.25, third[0].jsonPrimitive.double)
        assertEquals(-5.5, third[1].jsonPrimitive.double)
    }

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
