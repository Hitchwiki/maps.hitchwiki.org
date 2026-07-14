package org.hitchwiki.maps.data
import org.hitchwiki.maps.model.OsmRef
import org.hitchwiki.maps.model.SpotInfo
import kotlin.test.*

class SpotLinksTest {
    @Test fun allLinksInOrder() {
        val links = spotLinks(SpotInfo(
            osmId = 111L,
            carPooling = OsmRef(222L, "way"),
            fuel = OsmRef(333L, "node"),
            hitchwikiArticle = "https://hitchwiki.org/en/A",
            hitchwikiMap = "https://hitchwiki.org/maps/B",
        ))
        assertEquals(5, links.size)
        assertEquals("https://www.openstreetmap.org/node/111", links[0].url)
        assertEquals("https://www.openstreetmap.org/way/222", links[1].url)
        assertEquals("https://www.openstreetmap.org/node/333", links[2].url)
        assertEquals("https://hitchwiki.org/en/A", links[3].url)
        assertEquals("https://hitchwiki.org/maps/B", links[4].url)
        assertEquals("Official hitchhiking spot", links[0].label)
    }
    @Test fun emptySpotHasNoLinks() {
        assertTrue(spotLinks(SpotInfo()).isEmpty())
    }
    @Test fun onlyPresentLinksIncluded() {
        val links = spotLinks(SpotInfo(osmId = 9L, hitchwikiArticle = "https://x"))
        assertEquals(2, links.size)
        assertEquals("https://www.openstreetmap.org/node/9", links[0].url)
        assertEquals("https://x", links[1].url)
    }
}
