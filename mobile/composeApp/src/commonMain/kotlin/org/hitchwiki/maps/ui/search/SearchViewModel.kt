package org.hitchwiki.maps.ui.search
import org.hitchwiki.maps.data.RecentRidesSource
import org.hitchwiki.maps.model.RecentRide
import org.hitchwiki.maps.model.latLon
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class SearchViewModel(
    private val source: RecentRidesSource,
    private val scope: CoroutineScope,
    private val workDispatcher: CoroutineDispatcher = Dispatchers.Default,
) {
    private val _state = MutableStateFlow(SearchUiState())
    val state: StateFlow<SearchUiState> = _state.asStateFlow()

    // Full navigable set (valid coords only); results are a query view over this.
    private var all: List<RecentRide> = emptyList()

    fun load() {
        _state.update { it.copy(loading = true, error = null) }
        scope.launch {
            try {
                val list = withContext(workDispatcher) { source.recent().filter { it.latLon != null } }
                all = list
                _state.update { it.copy(loading = false, results = filtered(list, it.query)) }
            } catch (e: Throwable) {
                _state.update { it.copy(loading = false, error = e.message ?: "Failed to load recent rides") }
            }
        }
    }

    fun setQuery(q: String) = _state.update { it.copy(query = q, results = filtered(all, q)) }

    private fun filtered(list: List<RecentRide>, q: String): List<RecentRide> {
        val needle = q.trim().lowercase()
        if (needle.isEmpty()) return list
        return list.filter {
            it.hitchhikerName?.lowercase()?.contains(needle) == true ||
                it.text?.lowercase()?.contains(needle) == true
        }
    }
}
