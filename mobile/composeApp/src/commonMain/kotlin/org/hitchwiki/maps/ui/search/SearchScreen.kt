package org.hitchwiki.maps.ui.search
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import org.hitchwiki.maps.model.latLon
import org.hitchwiki.maps.model.sid
import org.hitchwiki.maps.ui.common.RecentRideRow

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SearchScreen(
    viewModel: SearchViewModel,
    onResult: (Double, Double, String) -> Unit,   // lat, lon, sid
    onBack: () -> Unit,
) {
    val state by viewModel.state.collectAsState()
    LaunchedEffect(Unit) { viewModel.load() }

    Scaffold(topBar = {
        TopAppBar(
            title = { Text(if (state.query.isBlank()) "Recent rides" else "Search") },
            navigationIcon = { TextButton(onClick = onBack) { Text("Back") } },
        )
    }) { padding ->
        Column(Modifier.fillMaxSize().padding(padding)) {
            OutlinedTextField(
                value = state.query,
                onValueChange = { viewModel.setQuery(it) },
                placeholder = { Text("Search by name or comment") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
            )
            when {
                state.loading -> Box(Modifier.fillMaxSize(), Alignment.Center) { CircularProgressIndicator() }
                state.error != null -> Text("Couldn't load recent rides: ${state.error}", Modifier.padding(16.dp))
                state.results.isEmpty() -> Text(
                    if (state.query.isBlank()) "No recent rides." else "No matches.",
                    Modifier.padding(16.dp),
                )
                else -> LazyColumn(Modifier.fillMaxSize()) {
                    items(state.results) { ride ->
                        // Only navigable rides are in results (invalid coords dropped at load).
                        val ll = ride.latLon
                        val sid = ride.sid
                        RecentRideRow(ride) { if (ll != null && sid != null) onResult(ll.first, ll.second, sid) }
                    }
                }
            }
        }
    }
}
