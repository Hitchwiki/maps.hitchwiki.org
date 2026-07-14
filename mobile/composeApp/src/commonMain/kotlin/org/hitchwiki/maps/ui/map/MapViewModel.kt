package org.hitchwiki.maps.ui.map
import org.hitchwiki.maps.data.SpotDetailSource
import org.hitchwiki.maps.data.SpotRepository
import org.hitchwiki.maps.data.buildSpotsGeoJson
import org.hitchwiki.maps.geo.LatLng
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

class MapViewModel(
    private val spots: SpotRepository,
    private val details: SpotDetailSource,
    private val scope: CoroutineScope,
) {
    private val _state = MutableStateFlow(MapUiState())
    val state: StateFlow<MapUiState> = _state.asStateFlow()

    // sid → Spot, built once per load so selectSpot is O(1) over ~35k spots.
    private var spotsBySid: Map<String, org.hitchwiki.maps.model.Spot> = emptyMap()

    fun load() {
        _state.update { it.copy(loading = true, error = null) }
        scope.launch {
            try {
                val fresh = spots.spots()
                // Build the (potentially 35k-feature) GeoJSON once here rather than inside the
                // update lambda, which MutableStateFlow.update may re-invoke on CAS contention.
                val geo = buildSpotsGeoJson(fresh)
                spotsBySid = fresh.associateBy { org.hitchwiki.maps.util.spotId(it.lat, it.lon) }
                _state.update { it.copy(loading = false, spots = fresh, geoJson = geo) }
            } catch (e: Throwable) {
                _state.update { it.copy(loading = false, error = e.message ?: "Failed to load spots") }
            }
        }
    }

    fun selectSpot(sid: String) {
        val s = spotsBySid[sid]
        _state.update { it.copy(
            selectedSid = sid, selectedDetail = null, detailLoading = true, detailError = null,
            selectedRating = s?.rating, selectedReviewCount = s?.reviewCount,
        ) }
        scope.launch {
            try {
                val d = details.detail(sid)
                // Ignore a late result if the user already selected/closed another spot.
                _state.update {
                    if (it.selectedSid == sid) it.copy(selectedDetail = d, detailLoading = false, detailError = null) else it
                }
            } catch (e: Throwable) {
                // Surface the failure instead of leaving detailLoading=false with no signal,
                // which the UI would otherwise render as a permanent "Loading…" sheet.
                _state.update {
                    if (it.selectedSid == sid) {
                        it.copy(detailLoading = false, detailError = e.message ?: "Failed to load spot details")
                    } else {
                        it
                    }
                }
            }
        }
    }

    fun clearSelection() = _state.update { it.copy(
        selectedSid = null, selectedDetail = null, detailLoading = false, detailError = null,
        selectedRating = null, selectedReviewCount = null,
    ) }

    fun onUserLocation(loc: LatLng) =
        _state.update { it.copy(userLocation = loc, cameraTarget = loc) }

    fun cameraConsumed() = _state.update { it.copy(cameraTarget = null) }
}
