package org.hitchwiki.maps.data
import org.hitchwiki.maps.model.SpotRide

// Newest-first by submissionTime (ISO strings sort lexicographically); null times go last.
fun ridesNewestFirst(rides: List<SpotRide>): List<SpotRide> =
    rides.sortedWith(compareByDescending(nullsFirst()) { it.submissionTime })
