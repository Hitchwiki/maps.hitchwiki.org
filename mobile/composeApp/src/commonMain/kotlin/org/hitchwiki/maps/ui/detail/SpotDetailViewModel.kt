package org.hitchwiki.maps.ui.detail
import org.hitchwiki.maps.data.SpotDetailSource
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch

class SpotDetailViewModel(
    private val sid: String,
    private val details: SpotDetailSource,
    private val scope: CoroutineScope,
) {
    private val _state = MutableStateFlow(SpotDetailUiState())
    val state: StateFlow<SpotDetailUiState> = _state.asStateFlow()

    fun load() {
        _state.update { it.copy(loading = true, error = null) }
        scope.launch {
            try {
                val d = details.detail(sid)
                _state.update { it.copy(loading = false, detail = d) }
            } catch (e: Throwable) {
                _state.update { it.copy(loading = false, error = e.message ?: "Failed to load spot") }
            }
        }
    }
}
