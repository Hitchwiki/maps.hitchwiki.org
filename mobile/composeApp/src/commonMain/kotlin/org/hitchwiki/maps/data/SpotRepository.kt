package org.hitchwiki.maps.data
import org.hitchwiki.maps.model.Spot

class SpotRepository(private val api: HitchwikiApi, private val cache: SpotCache) {
    /** Network-first: fetch, persist, return. On network failure fall back to the last
     *  cached copy (offline field use). Rethrow only when the cache is also empty. */
    suspend fun spots(forceRefresh: Boolean = false): List<Spot> {
        return try {
            val fresh = api.spots()
            cache.saveSpots(fresh)
            fresh
        } catch (e: Throwable) {
            val cached = cache.loadSpots()
            if (cached.isNotEmpty()) cached else throw e
        }
    }
}
