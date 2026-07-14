package org.hitchwiki.maps.ui.map
import org.hitchwiki.maps.geo.LatLng
import org.hitchwiki.maps.model.Spot
import org.hitchwiki.maps.model.SpotDetail

data class MapUiState(
    val loading: Boolean = false,
    val spots: List<Spot> = emptyList(),
    val geoJson: String = """{"type":"FeatureCollection","features":[]}""",
    val error: String? = null,
    val selectedSid: String? = null,
    val selectedDetail: SpotDetail? = null,
    val detailLoading: Boolean = false,
    val detailError: String? = null,
    val selectedRating: Double? = null,
    val selectedReviewCount: Int? = null,
    val userLocation: LatLng? = null,
    // Non-null when the map should animate to a new center; the map clears it after consuming.
    val cameraTarget: LatLng? = null,
)
