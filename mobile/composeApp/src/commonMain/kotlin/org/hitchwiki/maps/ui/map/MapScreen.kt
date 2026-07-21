package org.hitchwiki.maps.ui.map
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import org.hitchwiki.maps.map.MapCallbacks
import org.hitchwiki.maps.map.MapState
import org.hitchwiki.maps.map.PlatformMap

// PWA search-bar palette (style.css): white pill, Google-blue icons, grey placeholder.
private val PillColor = Color.White
private val IconBlue = Color(0xFF1A73E8)
private val PlaceholderGrey = Color(0xFF5F6368)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MapScreen(
    viewModel: MapViewModel,
    onRequestLocation: () -> Unit,
    onOpenDetail: (String, Float, Int) -> Unit,
    onOpenSearch: () -> Unit,
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

        // Required OSM US attribution. Padded off the nav bar so gesture insets don't cover it.
        Text(
            "© OpenStreetMap contributors, © OpenStreetMap US",
            style = MaterialTheme.typography.labelSmall,
            textAlign = TextAlign.End,
            modifier = Modifier.align(Alignment.BottomEnd).navigationBarsPadding().padding(4.dp),
        )

        if (state.loading) {
            CircularProgressIndicator(Modifier.align(Alignment.Center))
        }
        state.error?.let {
            // Sits below the search bar (which owns the top-center slot).
            Text("Couldn't load spots: $it",
                modifier = Modifier.align(Alignment.TopCenter).statusBarsPadding().padding(top = 76.dp, start = 16.dp, end = 16.dp))
        }

        FloatingActionButton(
            onClick = onRequestLocation,
            modifier = Modifier.align(Alignment.BottomStart).navigationBarsPadding().padding(16.dp),
        ) { Text("◎") }

        var showFilter by remember { mutableStateOf(false) }
        // PWA-style top search bar: tap the field to open search; the sliders icon opens filters.
        // statusBarsPadding keeps it below the system status bar (clock/network) on this
        // edge-to-edge activity.
        Surface(
            color = PillColor,
            shape = RoundedCornerShape(24.dp),
            shadowElevation = 4.dp,
            modifier = Modifier
                .align(Alignment.TopCenter)
                .statusBarsPadding()
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 12.dp)
                .height(48.dp),
        ) {
            Row(Modifier.fillMaxSize(), verticalAlignment = Alignment.CenterVertically) {
                // Search field region — its own hit target.
                Row(
                    Modifier.weight(1f).fillMaxHeight().clickable(onClick = onOpenSearch).padding(start = 16.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    MagnifierIcon(IconBlue)
                    Spacer(Modifier.width(12.dp))
                    Text("Search rides…", style = MaterialTheme.typography.bodyLarge, color = PlaceholderGrey)
                }
                // Filter button — full 48dp touch target, distinct from the search field.
                IconButton(onClick = { showFilter = true }, modifier = Modifier.size(48.dp)) {
                    SlidersIcon(IconBlue, active = state.filterState.isActive)
                }
                Spacer(Modifier.width(4.dp))
            }
        }

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

/** Magnifier glyph (mirrors the PWA geocoder icon) drawn as a vector so no icon font is needed. */
@Composable
private fun MagnifierIcon(tint: Color) {
    Canvas(Modifier.size(20.dp)) {
        val r = size.minDimension
        val stroke = r * 0.09f
        val lensR = r * 0.30f
        val c = Offset(r * 0.42f, r * 0.42f)
        drawCircle(color = tint, radius = lensR, center = c, style = Stroke(width = stroke))
        drawLine(
            tint,
            Offset(c.x + lensR * 0.72f, c.y + lensR * 0.72f),
            Offset(r * 0.86f, r * 0.86f),
            strokeWidth = stroke, cap = StrokeCap.Round,
        )
    }
}

/** Three-slider "tune" glyph (mirrors the PWA fa-sliders filter icon). A blue dot marks an
 *  active filter. Knobs get a white cut-out so they read as handles over the tracks. */
@Composable
private fun SlidersIcon(tint: Color, active: Boolean) {
    Canvas(Modifier.size(22.dp)) {
        val w = size.width
        val h = size.height
        val stroke = h * 0.085f
        val knobR = h * 0.14f
        val rowY = floatArrayOf(0.24f, 0.5f, 0.76f)
        val knobX = floatArrayOf(0.66f, 0.36f, 0.62f)
        for (i in 0..2) {
            val y = h * rowY[i]
            drawLine(tint, Offset(w * 0.12f, y), Offset(w * 0.88f, y), strokeWidth = stroke, cap = StrokeCap.Round)
            drawCircle(PillColor, radius = knobR + stroke * 0.7f, center = Offset(w * knobX[i], y))
            drawCircle(tint, radius = knobR, center = Offset(w * knobX[i], y))
        }
        if (active) drawCircle(IconBlue, radius = h * 0.12f, center = Offset(w * 0.9f, h * 0.12f))
    }
}
