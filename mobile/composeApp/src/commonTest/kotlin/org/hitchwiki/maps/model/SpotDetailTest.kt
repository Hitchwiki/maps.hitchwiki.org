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
}
