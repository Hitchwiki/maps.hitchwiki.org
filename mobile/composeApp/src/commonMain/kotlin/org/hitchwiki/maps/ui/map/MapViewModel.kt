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

    fun load() {
        _state.update { it.copy(loading = true, error = null) }
        scope.launch {
            try {
                val fresh = spots.spots()
                _state.update { it.copy(loading = false, spots = fresh, geoJson = buildSpotsGeoJson(fresh)) }
            } catch (e: Throwable) {
                _state.update { it.copy(loading = false, error = e.message ?: "Failed to load spots") }
            }
        }
    }

    fun selectSpot(sid: String) {
        _state.update { it.copy(selectedSid = sid, selectedDetail = null, detailLoading = true) }
        scope.launch {
            try {
                val d = details.detail(sid)
                // Ignore a late result if the user already selected/closed another spot.
                _state.update { if (it.selectedSid == sid) it.copy(selectedDetail = d, detailLoading = false) else it }
            } catch (e: Throwable) {
                _state.update { if (it.selectedSid == sid) it.copy(detailLoading = false) else it }
            }
        }
    }

    fun clearSelection() =
        _state.update { it.copy(selectedSid = null, selectedDetail = null, detailLoading = false) }

    fun onUserLocation(loc: LatLng) =
        _state.update { it.copy(userLocation = loc, cameraTarget = loc) }

    fun cameraConsumed() = _state.update { it.copy(cameraTarget = null) }
}
