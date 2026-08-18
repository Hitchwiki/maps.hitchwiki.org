package org.hitchwiki.maps.data
import app.cash.sqldelight.driver.jdbc.sqlite.JdbcSqliteDriver
import org.hitchwiki.maps.db.HitchwikiDb
import org.hitchwiki.maps.model.Spot
import kotlinx.coroutines.test.runTest
import kotlin.test.*

class SqlDelightSpotCacheTest {
    private fun newCache(): SqlDelightSpotCache {
        val driver = JdbcSqliteDriver(JdbcSqliteDriver.IN_MEMORY)
        HitchwikiDb.Schema.create(driver)
        return SqlDelightSpotCache(HitchwikiDb(driver))
    }
    @Test fun savesAndLoadsRoundTrip() = runTest {
        val cache = newCache()
        cache.saveSpots(listOf(
            Spot(lat = 1.0, lon = 2.0, rating = 4.0, reviewCount = 3, wiki = true),
            Spot(lat = 5.5, lon = 6.6, rating = 5.0, reviewCount = 1),
        ))
        val loaded = cache.loadSpots().sortedBy { it.lat }
        assertEquals(2, loaded.size)
        assertTrue(loaded[0].wiki); assertEquals(3, loaded[0].reviewCount); assertEquals(6.6, loaded[1].lon)
    }
    @Test fun saveReplacesPreviousSet() = runTest {
        val cache = newCache()
        cache.saveSpots(listOf(Spot(lat = 1.0, lon = 2.0, rating = 4.0, reviewCount = 3)))
        cache.saveSpots(listOf(Spot(lat = 9.0, lon = 9.0, rating = 5.0, reviewCount = 1)))
        val loaded = cache.loadSpots()
        assertEquals(1, loaded.size); assertEquals(9.0, loaded[0].lat)
    }
}
