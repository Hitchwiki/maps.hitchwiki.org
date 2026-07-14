package org.hitchwiki.maps.data
import kotlinx.serialization.encodeToString
import kotlinx.serialization.decodeFromString
import org.hitchwiki.maps.db.HitchwikiDb
import org.hitchwiki.maps.model.Spot

// Stores each Spot as its serialized JSON keyed by (lat, lon); a save replaces the whole
// set in one transaction so the cache always mirrors the latest spots.json.
// Note: the generated queries accessor is `spotCacheQueries`, derived from the .sq
// filename (SpotCache.sq), not `hitchwikiDbQueries` (the database name).
class SqlDelightSpotCache(private val db: HitchwikiDb) : SpotCache {
    override suspend fun saveSpots(spots: List<Spot>) {
        db.spotCacheQueries.transaction {
            db.spotCacheQueries.deleteAll()
            for (s in spots) db.spotCacheQueries.insert(s.lat, s.lon, appJson.encodeToString(s))
        }
    }
    override suspend fun loadSpots(): List<Spot> =
        db.spotCacheQueries.selectAll().executeAsList().map { appJson.decodeFromString<Spot>(it) }
}
