package org.hitchwiki.maps.util
import kotlinx.datetime.LocalDateTime

private val MONTHS = listOf(
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)

/** Format a ride's ISO timestamp for display as "Month YYYY". Ride timestamps come from
 *  Python isoformat() (e.g. "2024-01-15T14:30:00"). Returns "" for null/blank, and falls back
 *  to the first 10 chars (YYYY-MM-DD) if the value has no parseable time component. */
fun formatRideDate(iso: String?): String {
    if (iso.isNullOrBlank()) return ""
    return try {
        val dt = LocalDateTime.parse(iso)
        "${MONTHS[dt.monthNumber - 1]} ${dt.year}"
    } catch (e: Exception) {
        iso.take(10)
    }
}
