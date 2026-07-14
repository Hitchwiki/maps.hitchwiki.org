package org.hitchwiki.maps.map
import androidx.compose.foundation.layout.Box
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier

@Composable
actual fun PlatformMap(state: MapState, callbacks: MapCallbacks, modifier: Modifier) {
    // TODO(iOS bring-up): MapLibre iOS actual.
    Box(modifier)
}
