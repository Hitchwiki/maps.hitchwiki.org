package org.hitchwiki.maps.location
import org.hitchwiki.maps.geo.LatLng

/** Last-known device location, or null if unavailable/denied. */
expect class LocationProvider {
    suspend fun current(): LatLng?
}
