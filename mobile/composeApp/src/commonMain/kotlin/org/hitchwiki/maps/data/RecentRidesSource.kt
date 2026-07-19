package org.hitchwiki.maps.data
import org.hitchwiki.maps.model.RecentRide

/** Lazy source for the latest-rides list (spots_recent.json). Fetched only when Search opens. */
interface RecentRidesSource { suspend fun recent(): List<RecentRide> }

class ApiRecentRidesSource(private val api: HitchwikiApi) : RecentRidesSource {
    override suspend fun recent(): List<RecentRide> = api.recentRides()
}
