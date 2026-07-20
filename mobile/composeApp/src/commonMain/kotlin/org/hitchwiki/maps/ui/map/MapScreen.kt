package org.hitchwiki.maps.ui.map
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import org.hitchwiki.maps.map.MapCallbacks
import org.hitchwiki.maps.map.MapState
import org.hitchwiki.maps.map.PlatformMap

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MapScreen(
    viewModel: MapViewModel,
    onRequestLocation: () -> Unit,
    onOpenDetail: (String, Float, Int) -> Unit,
    modifier: Modifier = Modifier,
) {
    val state by viewModel.state.collectAsState()
    LaunchedEffect(Unit) { viewModel.load() }

    Box(modifier.fillMaxSize()) {
        PlatformMap(
            state = MapState(geoJson = state.geoJson, cameraTarget = state.cameraTarget),
            callbacks = MapCallbacks(
                onSpotClick = { sid -> viewModel.selectSpot(sid) },
                onCameraConsumed = { viewModel.cameraConsumed() },
            ),
            modifier = Modifier.fillMaxSize(),
        )

        // Required OSM US attribution.
        Text(
            "© OpenStreetMap contributors, © OpenStreetMap US",
            style = MaterialTheme.typography.labelSmall,
            textAlign = TextAlign.End,
            modifier = Modifier.align(Alignment.BottomEnd).padding(4.dp),
        )

        if (state.loading) {
            CircularProgressIndicator(Modifier.align(Alignment.Center))
        }
        state.error?.let {
            Text("Couldn't load spots: $it",
                modifier = Modifier.align(Alignment.TopCenter).padding(16.dp))
        }

        FloatingActionButton(
            onClick = onRequestLocation,
            modifier = Modifier.align(Alignment.BottomStart).padding(16.dp),
        ) { Text("◎") }

        var showFilter by remember { mutableStateOf(false) }
        FilledTonalButton(
            onClick = { showFilter = true },
            modifier = Modifier.align(Alignment.TopEnd).padding(16.dp),
        ) { Text(if (state.filterState.isActive) "⚙ Filters •" else "⚙ Filters") }

        if (showFilter) {
            FilterSheet(
                current = state.filterState,
                onApply = { viewModel.setFilter(it) },
                onDismiss = { showFilter = false },
            )
        }

        if (state.selectedSid != null) {
            SpotSummarySheet(
                state = state,
                onDismiss = { viewModel.clearSelection() },
                onOpenDetail = {
                    onOpenDetail(
                        state.selectedSid!!,
                        (state.selectedRating ?: 0.0).toFloat(),
                        state.selectedReviewCount ?: 0,
                    )
                },
            )
        }
    }
}
