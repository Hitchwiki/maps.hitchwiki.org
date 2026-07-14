package org.hitchwiki.maps.util

/** Spot id = lat/lon each fixed to 5 decimals, joined by '_'. Mirrors the backend's
 *  generate_spot_id and the rides/by-spot/<id>.json filename. Uses a manual formatter
 *  because kotlin common has no String.format. */
fun spotId(lat: Double, lon: Double): String = "${fixed5(lat)}_${fixed5(lon)}"

private fun fixed5(v: Double): String {
    // Round half-up to 5 decimals, then render with exactly 5 fractional digits.
    val scaled = kotlin.math.round(v * 100000.0).toLong()
    val sign = if (scaled < 0) "-" else ""
    val abs = kotlin.math.abs(scaled)
    val whole = abs / 100000
    val frac = (abs % 100000).toString().padStart(5, '0')
    return "$sign$whole.$frac"
}
