package org.hitchwiki.maps.map
import org.hitchwiki.maps.geo.LatLng

/** Everything the platform map needs to render, as platform-neutral data. */
data class MapState(val geoJson: String, val cameraTarget: LatLng?)

/** Callbacks from the platform map back into shared code. */
class MapCallbacks(
    val onSpotClick: (sid: String) -> Unit,
    val onCameraConsumed: () -> Unit,
)
