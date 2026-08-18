package org.hitchwiki.maps.data
import org.hitchwiki.maps.model.Spot

// Persistence seam: the repository depends on this, not on SQLDelight, so its
// offline-fallback logic is testable with an in-memory fake.
interface SpotCache {
    suspend fun saveSpots(spots: List<Spot>)
    suspend fun loadSpots(): List<Spot>
}
