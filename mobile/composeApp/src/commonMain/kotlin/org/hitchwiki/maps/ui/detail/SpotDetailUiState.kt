package org.hitchwiki.maps.ui.detail
import org.hitchwiki.maps.model.SpotDetail

data class SpotDetailUiState(
    val loading: Boolean = false,
    val detail: SpotDetail? = null,
    val error: String? = null,
)
