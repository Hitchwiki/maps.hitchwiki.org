package org.hitchwiki.maps.data
import org.hitchwiki.maps.model.Spot
import org.hitchwiki.maps.ui.map.FilterState

/** Pure filter over the in-memory spot list. Rating is Double; the threshold is an Int floor. */
fun applyFilters(spots: List<Spot>, f: FilterState): List<Spot> =
    if (!f.isActive) spots
    else spots.filter { s ->
        s.rating >= f.minRating &&
            (!f.osm || s.osm) && (!f.wiki || s.wiki) && (!f.cp || s.cp) && (!f.fuel || s.fuel)
    }
