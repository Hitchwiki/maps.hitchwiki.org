package org.hitchwiki.maps.data
import org.hitchwiki.maps.model.Spot
import org.hitchwiki.maps.ui.map.FilterState
import kotlin.test.*

class SpotFilterTest {
    private fun spot(rating: Double, osm: Boolean = false, wiki: Boolean = false,
                     cp: Boolean = false, fuel: Boolean = false) =
        Spot(lat = 1.0, lon = 2.0, rating = rating, reviewCount = 1,
             osm = osm, wiki = wiki, cp = cp, fuel = fuel)

    @Test fun inactiveFilterReturnsAll() {
        val spots = listOf(spot(1.0), spot(5.0))
        assertFalse(FilterState().isActive)
        assertEquals(spots, applyFilters(spots, FilterState()))
    }
    @Test fun minRatingKeepsAtOrAboveThreshold() {
        val spots = listOf(spot(2.0), spot(3.0), spot(4.0), spot(5.0))
        assertEquals(listOf(4.0, 5.0), applyFilters(spots, FilterState(minRating = 4)).map { it.rating })
    }
    @Test fun eachFlagRequiresPresence() {
        val spots = listOf(spot(5.0, osm = true), spot(5.0, wiki = true), spot(5.0))
        assertEquals(1, applyFilters(spots, FilterState(osm = true)).size)
        assertEquals(1, applyFilters(spots, FilterState(wiki = true)).size)
    }
    @Test fun combinedFlagsAndRatingAreAnded() {
        val spots = listOf(
            spot(5.0, osm = true, cp = true),
            spot(5.0, osm = true),
            spot(3.0, osm = true, cp = true),
        )
        val out = applyFilters(spots, FilterState(minRating = 4, osm = true, cp = true))
        assertEquals(1, out.size)
    }
    @Test fun isActiveDetectsAnyConstraint() {
        assertTrue(FilterState(minRating = 3).isActive)
        assertTrue(FilterState(fuel = true).isActive)
        assertFalse(FilterState().isActive)
    }
}
