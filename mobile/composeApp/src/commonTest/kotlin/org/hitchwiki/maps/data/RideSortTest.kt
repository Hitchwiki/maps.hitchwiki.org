package org.hitchwiki.maps.data
import org.hitchwiki.maps.model.SpotRide
import kotlin.test.*

class RideSortTest {
    private fun ride(id: String, t: String?) = SpotRide(id = id, submissionTime = t)
    @Test fun sortsNewestFirstNullsLast() {
        val sorted = ridesNewestFirst(listOf(
            ride("a", "2023-01-01T00:00:00"),
            ride("b", "2024-06-01T00:00:00"),
            ride("c", null),
            ride("d", "2024-01-01T00:00:00"),
        ))
        assertEquals(listOf("b", "d", "a", "c"), sorted.map { it.id })
    }
}
