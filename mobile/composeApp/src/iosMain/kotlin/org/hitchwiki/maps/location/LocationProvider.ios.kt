package org.hitchwiki.maps.location
import org.hitchwiki.maps.geo.LatLng

actual class LocationProvider {
    actual suspend fun current(): LatLng? = null
}
