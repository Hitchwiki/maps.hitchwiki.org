package org.hitchwiki.maps.data
import org.hitchwiki.maps.model.SpotDetail

/** Seam for fetching one spot's detail, so the map view-model is testable with a fake. */
interface SpotDetailSource { suspend fun detail(sid: String): SpotDetail }

class ApiSpotDetailSource(private val api: HitchwikiApi) : SpotDetailSource {
    override suspend fun detail(sid: String): SpotDetail = api.spotDetail(sid)
}
