package org.hitchwiki.maps.data
import org.hitchwiki.maps.model.Spot

class SpotRepository(private val api: HitchwikiApi, private val cache: SpotCache) {
    // Network-first: only the fetch is guarded, so a cache-write failure propagates
    // instead of masquerading as an offline event and returning stale data.
    suspend fun spots(forceRefresh: Boolean = false): List<Spot> {
        val fresh = try {
            api.spots()
        } catch (e: Throwable) {
            val cached = cache.loadSpots()
            return if (cached.isNotEmpty()) cached else throw e
        }
        cache.saveSpots(fresh)
        return fresh
    }
}
