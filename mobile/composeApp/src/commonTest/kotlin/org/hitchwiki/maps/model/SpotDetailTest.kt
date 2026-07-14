package org.hitchwiki.maps.model
import org.hitchwiki.maps.data.appJson
import kotlin.test.*

class SpotDetailTest {
    private val fixture = """
      {"spot":{"wait":12,"distance":34,"osm_id":123456,"hitchwiki_article":"https://hitchwiki.org/en/X"},
       "rides":[{"id":"src-abc","rating":5,"wait":10,"distance":34.2,"comment":"good spot",
                 "hitchhiker_name":"alice","submission_time":"2024-01-15T14:30:00",
                 "ride_datetime":"2024-01-15T14:00:00","arrival_datetime":null}]}
    """.trimIndent()

    @Test fun parsesSpotAndRides() {
        val d = appJson.decodeFromString<SpotDetail>(fixture)
        assertEquals(12, d.spot.wait); assertEquals(34, d.spot.distance)
        assertEquals(123456L, d.spot.osmId)
        assertEquals("https://hitchwiki.org/en/X", d.spot.hitchwikiArticle)
        assertNull(d.spot.carPooling)
        val r = d.rides.single()
        assertEquals("src-abc", r.id); assertEquals("alice", r.hitchhikerName)
        assertEquals(34.2, r.distance); assertNull(r.arrivalDatetime)
    }
    @Test fun emptySpotObjectOk() {
        val d = appJson.decodeFromString<SpotDetail>("""{"spot":{},"rides":[]}""")
        assertNull(d.spot.wait); assertTrue(d.rides.isEmpty())
    }

    // car_pooling and fuel are {id, osm_type} objects in the real per-spot JSON, not strings.
    // Parsing them into OsmRef is what unblocks the OSM link chips (and would crash as String?).
    @Test fun parsesCarPoolingAndFuelObjects() {
        val d = appJson.decodeFromString<SpotDetail>(
            """{"spot":{"car_pooling":{"id":123,"osm_type":"way"},"fuel":{"id":45,"osm_type":"node"}},"rides":[]}"""
        )
        assertEquals(123L, d.spot.carPooling?.id)
        assertEquals("way", d.spot.carPooling?.osmType)
        assertEquals(45L, d.spot.fuel?.id)
        assertEquals("node", d.spot.fuel?.osmType)
    }
}
