package org.hitchwiki.maps.model
import org.hitchwiki.maps.data.appJson
import kotlin.test.*

class SpotTest {
    private val fixture = """
      [{"lat":78.24684,"lon":15.49484,"rating":5.0,"review_count":1,"latest_ms":1730849926000,"dest_lats":[78.19898],"dest_lons":[15.79834]},
       {"lat":63.51291,"lon":10.85895,"rating":5.0,"review_count":1,"latest_ms":1688990217000,"wiki":true}]
    """.trimIndent()

    @Test fun parsesRequiredAndOptional() {
        val spots = appJson.decodeFromString<List<Spot>>(fixture)
        assertEquals(2, spots.size)
        val a = spots[0]
        assertEquals(78.24684, a.lat); assertEquals(1, a.reviewCount)
        assertEquals(1730849926000L, a.latestMs); assertEquals(listOf(78.19898), a.destLats)
        assertFalse(a.wiki)
    }
    @Test fun missingFlagsDefaultFalse_presentFlagTrue() {
        val spots = appJson.decodeFromString<List<Spot>>(fixture)
        assertTrue(spots[1].wiki)
        assertFalse(spots[1].osm); assertFalse(spots[1].cp)
        assertNull(spots[1].destLats)
    }
}
