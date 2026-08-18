package org.hitchwiki.maps.model
import org.hitchwiki.maps.data.appJson
import kotlin.test.*

class RecentRideTest {
    @Test fun parsesRealRecordShape() {
        val r = appJson.decodeFromString<RecentRide>(
            """{"url":"#52.50374,13.27900","submission_time":"2026-06-29 08:37:21 🕒",
                "hitchhiker_name":"Anonymous","rating":5,"distance":null,"text":"Nice spot"}"""
        )
        assertEquals("Anonymous", r.hitchhikerName)
        assertEquals(5, r.rating)
        assertNull(r.distance)
        assertEquals("Nice spot", r.text)
    }
    @Test fun derivesLatLonAndSidFromUrl() {
        val r = appJson.decodeFromString<RecentRide>("""{"url":"#52.50374,13.27900"}""")
        assertEquals(52.50374 to 13.27900, r.latLon)
        assertEquals("52.50374_13.27900", r.sid)
    }
    @Test fun malformedUrlYieldsNullNotCrash() {
        assertNull(appJson.decodeFromString<RecentRide>("""{"url":"#nope"}""").latLon)
        assertNull(appJson.decodeFromString<RecentRide>("""{"url":""}""").sid)
        assertNull(appJson.decodeFromString<RecentRide>("""{"url":"#1.0,2.0,3.0"}""").latLon)
    }
}
