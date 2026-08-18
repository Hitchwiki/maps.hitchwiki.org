package org.hitchwiki.maps.map
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier

/** The platform map surface. Android renders MapLibre; iOS is a stub for now. */
@Composable
expect fun PlatformMap(state: MapState, callbacks: MapCallbacks, modifier: Modifier)
