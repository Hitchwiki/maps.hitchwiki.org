package org.hitchwiki.maps.map

import android.graphics.Point
import android.graphics.RectF
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.viewinterop.AndroidView
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import org.maplibre.android.MapLibre
import org.maplibre.android.camera.CameraUpdateFactory
import org.maplibre.android.geometry.LatLng as MlLatLng
import org.maplibre.android.maps.MapLibreMap
import org.maplibre.android.maps.MapView
import org.maplibre.android.maps.Style
import org.maplibre.android.style.expressions.Expression
import org.maplibre.android.style.layers.CircleLayer
import org.maplibre.android.style.layers.PropertyFactory
import org.maplibre.android.style.layers.SymbolLayer
import org.maplibre.android.style.sources.GeoJsonOptions
import org.maplibre.android.style.sources.GeoJsonSource
import org.maplibre.geojson.Point as GjPoint

private const val SRC = "spots"
private const val LYR_CLUSTER = "spots-clusters"
private const val LYR_CLUSTER_COUNT = "spots-cluster-count"
private const val LYR_POINT = "spots-points"

@Composable
actual fun PlatformMap(state: MapState, callbacks: MapCallbacks, modifier: Modifier) {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    // The click listener below is registered once inside AndroidView's `factory` and would
    // otherwise close over the `callbacks` instance from the FIRST composition -- MapScreen
    // creates a fresh MapCallbacks on every recomposition, so a stale closure would silently
    // stop forwarding clicks to the current callbacks. rememberUpdatedState keeps a live pointer
    // the once-registered listener can read at call time instead.
    val currentCallbacks = rememberUpdatedState(callbacks)

    // MapView is created once (outside AndroidView's factory) so both the lifecycle-forwarding
    // DisposableEffect below and AndroidView's factory can reference the same instance.
    val mapView = remember {
        MapLibre.getInstance(context)
        MapView(context).apply { onCreate(null) }
    }
    // Holds the ready MapLibreMap so the `update` block can push new GeoJSON/camera changes
    // directly instead of calling getMapAsync again, which would re-run the style/layer/listener
    // setup on every recomposition (getMapAsync's callback fires immediately once the map is
    // already ready) and risk double-registering the click listener.
    val mapRef = remember { mutableStateOf<MapLibreMap?>(null) }
    // Tracks the last GeoJSON string actually pushed to the source, so `update` can skip
    // re-parsing the multi-MB (~35k-feature) source on every recomposition when it hasn't changed.
    val lastPushed = remember { androidx.compose.runtime.mutableStateOf<String?>(null) }

    // MapLibre's MapView needs Activity/Fragment lifecycle events forwarded to it (it manages a
    // native GL context that must start/stop with the surrounding lifecycle) -- AndroidView's
    // factory/onRelease alone only cover the view's creation/removal, not pause/resume/stop.
    // Forward the Compose lifecycle owner's events to the MapView, and guard against calling
    // onDestroy() twice (once from ON_DESTROY, once from onDispose if the composable leaves
    // composition before the owner is destroyed).
    DisposableEffect(lifecycleOwner, mapView) {
        var destroyed = false
        val observer = LifecycleEventObserver { _, event ->
            when (event) {
                Lifecycle.Event.ON_START -> mapView.onStart()
                Lifecycle.Event.ON_RESUME -> mapView.onResume()
                Lifecycle.Event.ON_PAUSE -> mapView.onPause()
                Lifecycle.Event.ON_STOP -> mapView.onStop()
                Lifecycle.Event.ON_DESTROY -> {
                    mapView.onDestroy()
                    destroyed = true
                }
                else -> {}
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose {
            lifecycleOwner.lifecycle.removeObserver(observer)
            if (!destroyed) mapView.onDestroy()
        }
    }

    AndroidView(
        modifier = modifier,
        factory = {
            // Runs once per MapView instance: registers the style/layers/click-listener exactly
            // once. Recompositions update the already-ready map via mapRef in the `update` block.
            // Style/tile loads happen off the setStyle callback's control flow (network fetches,
            // asset parsing), so a failure would otherwise leave a silently blank map -- surface
            // it to logcat for the manual emulator test.
            mapView.addOnDidFailLoadingMapListener { errorMessage ->
                android.util.Log.e("PlatformMap", "Map failed to load: $errorMessage")
            }
            mapView.getMapAsync { map ->
                mapRef.value = map
                // The compass defaults to the top-right, where it hides under the status bar and
                // search pill. Drop it below the search bar (top-right) so it's fully on-screen.
                val d = context.resources.displayMetrics.density
                map.uiSettings.setCompassMargins(0, (150 * d).toInt(), (16 * d).toInt(), 0)
                map.setStyle(Style.Builder().fromUri("asset://osm_us_style.json")) { style ->
                    val source = GeoJsonSource(
                        SRC, state.geoJson,
                        // clusterMaxZoom 11: above it, spots always render individually (was 13,
                        // which forced zooming in ~2 extra levels for single-spot granularity).
                        // clusterRadius 44 (px) breaks clusters apart a little sooner too.
                        GeoJsonOptions().withCluster(true).withClusterMaxZoom(11).withClusterRadius(44),
                    )
                    style.addSource(source)

                    // Cluster circles: sized by point_count (no text -> no glyphs).
                    style.addLayer(
                        CircleLayer(LYR_CLUSTER, SRC).apply {
                            setFilter(Expression.has("point_count"))
                            setProperties(
                                PropertyFactory.circleColor(android.graphics.Color.parseColor("#4464ad")),
                                PropertyFactory.circleRadius(
                                    Expression.step(
                                        Expression.get("point_count"),
                                        Expression.literal(14f),
                                        Expression.stop(50, 20f), Expression.stop(500, 28f),
                                    ),
                                ),
                                PropertyFactory.circleOpacity(0.85f),
                            )
                        },
                    )

                    // Cluster-count numbers: drawn on top of the cluster circles.
                    style.addLayer(
                        SymbolLayer(LYR_CLUSTER_COUNT, SRC).apply {
                            setFilter(Expression.has("point_count"))
                            setProperties(
                                // Cap the label at "999+" so large clusters never overflow the
                                // circle; below 1000 show the exact count.
                                PropertyFactory.textField(
                                    Expression.switchCase(
                                        Expression.gte(Expression.get("point_count"), Expression.literal(1000)),
                                        Expression.literal("999+"),
                                        Expression.toString(Expression.get("point_count")),
                                    ),
                                ),
                                PropertyFactory.textFont(arrayOf("Noto Sans Regular")),
                                PropertyFactory.textSize(12f),
                                PropertyFactory.textColor(android.graphics.Color.WHITE),
                                PropertyFactory.textAllowOverlap(true),
                                PropertyFactory.textIgnorePlacement(true),
                            )
                        },
                    )

                    // Unclustered points: colored by rating.
                    style.addLayer(
                        CircleLayer(LYR_POINT, SRC).apply {
                            setFilter(Expression.not(Expression.has("point_count")))
                            setProperties(
                                PropertyFactory.circleRadius(6f),
                                PropertyFactory.circleStrokeWidth(1f),
                                PropertyFactory.circleStrokeColor(android.graphics.Color.WHITE),
                                PropertyFactory.circleColor(
                                    Expression.step(
                                        Expression.get("rating"),
                                        Expression.literal("#c62828"), // < 3
                                        Expression.stop(3, "#f9a825"), // == 3
                                        Expression.stop(4, "#2e7d32"), // >= 4
                                    ),
                                ),
                            )
                        },
                    )

                    map.addOnMapClickListener { point ->
                        val screen = map.projection.toScreenLocation(point)
                        // A single-pixel hit test makes the 6px markers hard to tap. Query a
                        // finger-sized box (~24dp) around the tap and, when several spots fall in
                        // it, pick the one nearest the tap so the closest marker always wins.
                        val slop = 24f * context.resources.displayMetrics.density
                        val box = RectF(screen.x - slop, screen.y - slop, screen.x + slop, screen.y + slop)
                        val hits = map.queryRenderedFeatures(box, LYR_POINT)
                        val nearest = hits.minByOrNull { f ->
                            val g = f.geometry() as? GjPoint ?: return@minByOrNull Float.MAX_VALUE
                            val p = map.projection.toScreenLocation(MlLatLng(g.latitude(), g.longitude()))
                            val dx = p.x - screen.x
                            val dy = p.y - screen.y
                            dx * dx + dy * dy
                        }
                        val sid = nearest?.getStringProperty("sid")
                        if (sid != null) {
                            currentCallbacks.value.onSpotClick(sid)
                            return@addOnMapClickListener true
                        }
                        // Tapped a cluster? zoom in one step to expand it.
                        val clusterHit = map.queryRenderedFeatures(box, LYR_CLUSTER).isNotEmpty()
                        if (clusterHit) {
                            // CameraUpdateFactory.zoomBy(double, Point) takes the integer-pixel
                            // android.graphics.Point at 11.5.0, not the PointF that
                            // projection.toScreenLocation() returns -- round it.
                            map.animateCamera(
                                CameraUpdateFactory.zoomBy(2.0, Point(screen.x.toInt(), screen.y.toInt())),
                            )
                            true
                        } else {
                            false
                        }
                    }
                }
            }
            mapView
        },
        update = { _ ->
            // On recomposition, push the latest GeoJSON to the existing source and consume any
            // pending camera target via the already-ready map, without touching style/layers/listeners.
            mapRef.value?.let { m ->
                if (lastPushed.value != state.geoJson) {
                    android.util.Log.d("HitchwikiMap", "setGeoJson len=${state.geoJson.length}")
                    m.style?.getSourceAs<GeoJsonSource>(SRC)?.setGeoJson(state.geoJson)
                    lastPushed.value = state.geoJson
                    android.util.Log.d("HitchwikiMap", "setGeoJson done")
                }
                state.cameraTarget?.let {
                    m.animateCamera(CameraUpdateFactory.newLatLngZoom(MlLatLng(it.lat, it.lon), 12.0))
                    callbacks.onCameraConsumed()
                }
            }
        },
    )
}
