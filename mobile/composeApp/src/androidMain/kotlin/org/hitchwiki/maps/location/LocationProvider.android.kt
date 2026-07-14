package org.hitchwiki.maps.location
import android.annotation.SuppressLint
import android.content.Context
import com.google.android.gms.location.LocationServices
import kotlinx.coroutines.suspendCancellableCoroutine
import org.hitchwiki.maps.geo.LatLng
import kotlin.coroutines.resume

actual class LocationProvider(private val context: Context) {
    // Caller (Task 7) requests permission before invoking; annotate to satisfy lint.
    @SuppressLint("MissingPermission")
    actual suspend fun current(): LatLng? = suspendCancellableCoroutine { cont ->
        val client = LocationServices.getFusedLocationProviderClient(context)
        client.lastLocation
            .addOnSuccessListener { loc -> cont.resume(loc?.let { LatLng(it.latitude, it.longitude) }) }
            .addOnFailureListener { cont.resume(null) }
    }
}
