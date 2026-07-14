package org.hitchwiki.maps.model
import org.hitchwiki.maps.data.appJson
import kotlin.test.*

class RideIndexEntryTest {
    private val fixture = """
      [{"id":"liftershalte.info-83b5f328","sid":"38.65081_68.76809","lat":38.65081,"lon":68.76809,
        "u":"Anonymous","t":null,"r":5,"km":null,"w":20,"osm":false,"wiki":false,"cp":false,
        "v":null,"m":null,"rd":null,"c":null}]
    """.trimIndent()

    @Test fun parsesShortKeys() {
        val e = appJson.decodeFromString<List<RideIndexEntry>>(fixture).single()
        assertEquals("liftershalte.info-83b5f328", e.id)
        assertEquals("38.65081_68.76809", e.sid)
        assertEquals("Anonymous", e.user)
        assertNull(e.submittedMs); assertEquals(5, e.rating); assertNull(e.distanceKm)
        assertEquals(20, e.waitMin); assertFalse(e.osm)
        assertNull(e.vehicleKind); assertNull(e.signalMethods); assertNull(e.comment)
    }
}
