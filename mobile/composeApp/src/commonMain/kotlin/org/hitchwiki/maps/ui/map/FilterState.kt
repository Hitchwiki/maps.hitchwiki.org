package org.hitchwiki.maps.ui.map

/** Map-marker filter. minRating 0 == "Any"; flags require the corresponding Spot flag. */
data class FilterState(
    val minRating: Int = 0,
    val osm: Boolean = false,
    val wiki: Boolean = false,
    val cp: Boolean = false,
    val fuel: Boolean = false,
) {
    val isActive: Boolean get() = minRating > 0 || osm || wiki || cp || fuel
}
