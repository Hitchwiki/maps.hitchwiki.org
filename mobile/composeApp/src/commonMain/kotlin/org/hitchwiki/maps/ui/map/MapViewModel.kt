package org.hitchwiki.maps.ui.map
import org.hitchwiki.maps.data.SpotDetailSource
import org.hitchwiki.maps.data.SpotRepository
import org.hitchwiki.maps.data.applyFilters
import org.hitchwiki.maps.data.buildSpotsGeoJson
import org.hitchwiki.maps.geo.LatLng
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class MapViewModel(
    private val spots: SpotRepository,
    private val details: SpotDetailSource,
    private val scope: CoroutineScope,
    // The dispatcher for the heavy off-main load work. Defaults to the background pool in
    // production; tests inject a scheduler-backed dispatcher so advanceUntilIdle() stays
    // deterministic (a real Dispatchers.Default thread would escape the test scheduler).
    private val workDispatcher: CoroutineDispatcher = Dispatchers.Default,
) {
    private val _state = MutableStateFlow(MapUiState())
    val state: StateFlow<MapUiState> = _state.asStateFlow()

    // sid → Spot, built once per load so selectSpot is O(1) over ~35k spots.
    private var spotsBySid: Map<String, org.hitchwiki.maps.model.Spot> = emptyMap()

    fun load() {
        _state.update { it.copy(loading = true, error = null) }
        scope.launch {
            try {
                println("HitchwikiLoad: fetching spots")
                // The heavy load work — a ~35k-row SQLite read/write plus building a ~4.7MB
                // GeoJSON string plus a 35k-entry index — MUST run off the main thread. `scope`
                // is the Activity's lifecycleScope (Dispatchers.Main), so doing this inline
                // blocks the UI thread ~30s on a cold cache, which the system reports as an ANR
                // (the "first-run crash"). Default is the background pool available in commonMain
                // (Dispatchers.IO is JVM/Native-only, not in common). StateFlow.update below is
                // thread-safe and cheap, so it stays on the launch's Main context.
                val loaded = withContext(workDispatcher) {
                    val fresh = spots.spots()
                    println("HitchwikiLoad: got ${fresh.size} spots")
                    val geo = buildSpotsGeoJson(applyFilters(fresh, _state.value.filterState))
                    println("HitchwikiLoad: built geojson len=${geo.length}")
                    val bySid = fresh.associateBy { org.hitchwiki.maps.util.spotId(it.lat, it.lon) }
                    LoadResult(fresh, geo, bySid)
                }
                spotsBySid = loaded.bySid
                _state.update { it.copy(loading = false, spots = loaded.spots, geoJson = loaded.geoJson) }
                println("HitchwikiLoad: state updated")
            } catch (e: Throwable) {
                println("HitchwikiLoad: FAILED ${e::class.simpleName}: ${e.message}")
                _state.update { it.copy(loading = false, error = e.message ?: "Failed to load spots") }
            }
        }
    }

    /** Re-filter the already-loaded spots and rebuild the clustered source off-main. spotsBySid
     *  stays on the full set, so focusSpot still resolves a currently-filtered-out spot. */
    fun setFilter(state: FilterState) {
        _state.update { it.copy(filterState = state) }
        scope.launch {
            val full = _state.value.spots
            val geo = withContext(workDispatcher) { buildSpotsGeoJson(applyFilters(full, state)) }
            _state.update { it.copy(geoJson = geo) }
        }
    }

    /** Center the map on a spot (from a search/recent result) and open its summary sheet. */
    fun focusSpot(lat: Double, lon: Double, sid: String) {
        _state.update { it.copy(cameraTarget = LatLng(lat, lon)) }
        selectSpot(sid)
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

    // Carries the three products of the off-main load out of the background `withContext`.
    private class LoadResult(
        val spots: List<org.hitchwiki.maps.model.Spot>,
        val geoJson: String,
        val bySid: Map<String, org.hitchwiki.maps.model.Spot>,
    )
}
