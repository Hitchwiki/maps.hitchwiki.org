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
fun MapScreen(viewModel: MapViewModel, onRequestLocation: () -> Unit, modifier: Modifier = Modifier) {
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

        // Minimal detail summary (full sheet is P3).
        if (state.selectedSid != null) {
            val d = state.selectedDetail
            ModalBottomSheet(onDismissRequest = { viewModel.clearSelection() }) {
                Column(Modifier.fillMaxWidth().padding(16.dp)) {
                    if (state.detailLoading || d == null) {
                        Text("Loading…")
                    } else {
                        Text("Spot", style = MaterialTheme.typography.titleMedium)
                        d.spot.wait?.let { Text("Avg wait: $it min") }
                        d.spot.distance?.let { Text("Avg ride: $it km") }
                        Text("Rides logged: ${d.rides.size}")
                    }
                    Spacer(Modifier.height(24.dp))
                }
            }
        }
    }
}
