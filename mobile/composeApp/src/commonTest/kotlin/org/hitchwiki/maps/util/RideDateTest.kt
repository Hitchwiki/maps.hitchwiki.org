package org.hitchwiki.maps.util
import kotlin.test.*

class RideDateTest {
    @Test fun formatsFullIsoAsMonthYear() {
        assertEquals("January 2024", formatRideDate("2024-01-15T14:30:00"))
        assertEquals("December 2023", formatRideDate("2023-12-01T00:00:00"))
    }
    @Test fun nullOrBlankIsEmpty() {
        assertEquals("", formatRideDate(null))
        assertEquals("", formatRideDate(""))
    }
    @Test fun unparseableFallsBackToDatePrefix() {
        // A date-only string has no time component, so LocalDateTime.parse fails → prefix fallback.
        assertEquals("2024-01-15", formatRideDate("2024-01-15"))
    }
}
