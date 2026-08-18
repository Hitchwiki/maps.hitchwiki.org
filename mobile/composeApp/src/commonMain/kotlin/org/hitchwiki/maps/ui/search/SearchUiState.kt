package org.hitchwiki.maps.ui.search
import org.hitchwiki.maps.model.RecentRide

data class SearchUiState(
    val loading: Boolean = false,
    val query: String = "",
    val results: List<RecentRide> = emptyList(),
    val error: String? = null,
)
