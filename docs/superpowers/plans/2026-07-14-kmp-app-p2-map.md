# KMP App P2 — Map + Spot Markers (Android) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the placeholder screen with a MapLibre map on the OSM US vector basemap that draws all live spots as clustered markers, opens a minimal detail summary on tap, and has a current-location button — on Android (iOS map stubbed but compiling).

**Architecture:** A testable shared core in `commonMain` (`buildSpotsGeoJson` pure converter + `MapViewModel` state machine over the P1 `SpotRepository`) drives a platform map surface exposed via `expect fun PlatformMap(...)`. The Android `actual` hosts a MapLibre `MapView` in an `AndroidView`, feeds it one GeoJSON source with GPU clustering, and reports taps back. iOS `actual` is a stub so the target keeps compiling.

**Tech Stack:** Kotlin 2.1.0, Compose Multiplatform 1.7.3, MapLibre `org.maplibre.gl:android-sdk:11.5.0` (from the P1 spike), Ktor 3.0.1, kotlinx-serialization-json 1.7.3, kotlinx-coroutines 1.9.0, SQLDelight 2.0.2, JUnit4 + kotlin-test. Backend: OSM US Tileservice.

## Global Constraints

- **MVP is Android-only.** iOS is design-only: keep every platform type behind `expect/actual`, keep `iosSimulatorArm64` compiling, do not run/test iOS. A change that breaks the iOS compile is a failure.
- **MapLibre must never be referenced from `commonMain`.** Only `androidMain` may import `org.maplibre.*`. Shared code passes a GeoJSON **String**, plain `LatLng`/camera data types, and callbacks across the seam.
- **Basemap = OSM US Tileservice, no API key.** Vector TileJSON: `https://tiles.openstreetmap.us/vector/openmaptiles.json` (OpenMapTiles schema). Show attribution "© OpenStreetMap contributors, © OpenStreetMap US" on the map.
- **P2 uses CircleLayers only — no SymbolLayer, no text, no glyphs.** Clusters are circles sized by `point_count`; unclustered points are circles colored by rating. Cluster-count numbers and place-name labels (which need a glyphs URL) are deferred to P3. The bundled style.json therefore contains no symbol/text layers and needs no `glyphs`.
- **Marker rating colors:** green `#2e7d32` for rating ≥ 4, amber `#f9a825` for rating = 3, red `#c62828` for rating < 3.
- **Live data.** Spots come from the P1 `SpotRepository` against `https://maps.hitchwiki.org`; no bundled sample data.
- **Reuse P1, don't fork it.** `Spot`, `SpotDetail`, `HitchwikiApi`, `SpotRepository`, `SpotCache`/`SqlDelightSpotCache`, `DatabaseDriverFactory`, `appJson`, `spotId` already exist — consume them.
- **Coordinate order in GeoJSON is `[lon, lat]`** (GeoJSON spec), not `[lat, lon]`.
- **TDD, DRY, YAGNI, frequent commits.** Tasks 1–2 are red→green→commit. Tasks 3–7 are Android/Compose integration whose "test" is a successful build + a named manual check; commit each.
- Package root `org.hitchwiki.maps`.

---

## File Structure

```
mobile/composeApp/src/
├── commonMain/kotlin/org/hitchwiki/maps/
│   ├── geo/LatLng.kt                     shared coordinate + camera types
│   ├── data/GeoJson.kt                   buildSpotsGeoJson(spots): String   [Task 1]
│   ├── data/SpotDetailSource.kt          interface + ApiSpotDetailSource     [Task 2]
│   ├── ui/map/MapUiState.kt              UI state data class                 [Task 2]
│   ├── ui/map/MapViewModel.kt            state machine over SpotRepository   [Task 2]
│   ├── map/PlatformMap.kt                expect fun PlatformMap(...)          [Task 3]
│   ├── map/MapContracts.kt               MapState / MapCallbacks             [Task 3]
│   ├── location/LocationProvider.kt      expect class LocationProvider       [Task 3]
│   └── ui/map/MapScreen.kt               Compose screen: map + overlay       [Task 4]
├── commonTest/kotlin/org/hitchwiki/maps/
│   ├── data/GeoJsonTest.kt                                                   [Task 1]
│   └── ui/map/MapViewModelTest.kt                                            [Task 2]
├── androidMain/
│   ├── kotlin/org/hitchwiki/maps/
│   │   ├── map/PlatformMap.android.kt     MapLibre actual                    [Task 5]
│   │   ├── location/LocationProvider.android.kt                             [Task 6]
│   │   └── MainActivity.kt                build deps + MapScreen             [Task 7]
│   ├── assets/osm_us_style.json           bundled label-free style          [Task 5]
│   └── AndroidManifest.xml                INTERNET + location perms          [Task 6]
└── iosMain/kotlin/org/hitchwiki/maps/
    ├── map/PlatformMap.ios.kt             stub                              [Task 3]
    └── location/LocationProvider.ios.kt   stub                              [Task 3]
```

---

## Task 1: `buildSpotsGeoJson` — pure spots→GeoJSON converter

**Files:**
- Create: `mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/geo/LatLng.kt`
- Create: `mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/data/GeoJson.kt`
- Test: `mobile/composeApp/src/commonTest/kotlin/org/hitchwiki/maps/data/GeoJsonTest.kt`

**Interfaces:**
- Consumes: `Spot` (P1), `spotId` (P1), `appJson` (P1).
- Produces: `data class LatLng(val lat: Double, val lon: Double)`; `fun buildSpotsGeoJson(spots: List<Spot>): String` — a FeatureCollection where each feature is a Point at `[lon, lat]` with properties `sid` (String, from `spotId`) and `rating` (Double).

- [ ] **Step 1: Write the failing test**

```kotlin
package org.hitchwiki.maps.data
import org.hitchwiki.maps.model.Spot
import kotlinx.serialization.json.*
import kotlin.test.*

class GeoJsonTest {
    @Test fun emptyListIsEmptyFeatureCollection() {
        val fc = appJson.parseToJsonElement(buildSpotsGeoJson(emptyList())).jsonObject
        assertEquals("FeatureCollection", fc["type"]!!.jsonPrimitive.content)
        assertEquals(0, fc["features"]!!.jsonArray.size)
    }
    @Test fun oneSpotBecomesOneLonLatPointFeature() {
        val spots = listOf(Spot(lat = 51.0817, lon = 13.73629, rating = 5.0, reviewCount = 2))
        val fc = appJson.parseToJsonElement(buildSpotsGeoJson(spots)).jsonObject
        val feat = fc["features"]!!.jsonArray.single().jsonObject
        assertEquals("Feature", feat["type"]!!.jsonPrimitive.content)
        val coords = feat["geometry"]!!.jsonObject["coordinates"]!!.jsonArray
        // GeoJSON order is [lon, lat]
        assertEquals(13.73629, coords[0].jsonPrimitive.double)
        assertEquals(51.0817, coords[1].jsonPrimitive.double)
        val props = feat["properties"]!!.jsonObject
        assertEquals("51.08170_13.73629", props["sid"]!!.jsonPrimitive.content)
        assertEquals(5.0, props["rating"]!!.jsonPrimitive.double)
    }
    @Test fun featureCountMatchesInput() {
        val spots = List(3) { Spot(lat = it.toDouble(), lon = it.toDouble(), rating = 3.0, reviewCount = 1) }
        val fc = appJson.parseToJsonElement(buildSpotsGeoJson(spots)).jsonObject
        assertEquals(3, fc["features"]!!.jsonArray.size)
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mobile && ./gradlew :composeApp:testDebugUnitTest --tests "org.hitchwiki.maps.data.GeoJsonTest"`
Expected: FAIL — `buildSpotsGeoJson` / `LatLng` unresolved.

- [ ] **Step 3: Implement**

`geo/LatLng.kt`:
```kotlin
package org.hitchwiki.maps.geo

/** A plain lat/lon pair shared across the expect/actual map seam (no MapLibre type in commonMain). */
data class LatLng(val lat: Double, val lon: Double)
```

`data/GeoJson.kt`:
```kotlin
package org.hitchwiki.maps.data
import org.hitchwiki.maps.model.Spot
import org.hitchwiki.maps.util.spotId
import kotlinx.serialization.json.*

/** Build a GeoJSON FeatureCollection string for MapLibre's clustered GeoJsonSource.
 *  Each spot → a Point at [lon, lat] (GeoJSON order) with `sid` (for the tap→detail lookup)
 *  and `rating` (for the color ramp). Returned as a String so no MapLibre type leaks into
 *  commonMain — the Android actual feeds the String straight into GeoJsonSource. */
fun buildSpotsGeoJson(spots: List<Spot>): String {
    val features = spots.map { s ->
        buildJsonObject {
            put("type", "Feature")
            putJsonObject("geometry") {
                put("type", "Point")
                putJsonArray("coordinates") { add(s.lon); add(s.lat) }
            }
            putJsonObject("properties") {
                put("sid", spotId(s.lat, s.lon))
                put("rating", s.rating)
            }
        }
    }
    val fc = buildJsonObject {
        put("type", "FeatureCollection")
        put("features", JsonArray(features))
    }
    return fc.toString()
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd mobile && ./gradlew :composeApp:testDebugUnitTest --tests "org.hitchwiki.maps.data.GeoJsonTest"`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/geo/LatLng.kt \
        mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/data/GeoJson.kt \
        mobile/composeApp/src/commonTest/kotlin/org/hitchwiki/maps/data/GeoJsonTest.kt
git commit -m "feat(mobile): buildSpotsGeoJson pure spots->FeatureCollection converter"
```

---

## Task 2: `MapViewModel` state machine + `SpotDetailSource`

**Files:**
- Create: `mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/data/SpotDetailSource.kt`
- Create: `mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/ui/map/MapUiState.kt`
- Create: `mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/ui/map/MapViewModel.kt`
- Test: `mobile/composeApp/src/commonTest/kotlin/org/hitchwiki/maps/ui/map/MapViewModelTest.kt`

**Interfaces:**
- Consumes: `SpotRepository` (P1), `HitchwikiApi` (P1), `SpotDetail`/`Spot` (P1), `buildSpotsGeoJson`/`LatLng` (Task 1).
- Produces:
  - `interface SpotDetailSource { suspend fun detail(sid: String): SpotDetail }` + `class ApiSpotDetailSource(api: HitchwikiApi) : SpotDetailSource`.
  - `data class MapUiState(...)` (see code).
  - `class MapViewModel(spots: SpotRepository, details: SpotDetailSource, scope: CoroutineScope)` with `val state: StateFlow<MapUiState>`, `fun load()`, `fun selectSpot(sid)`, `fun clearSelection()`, `fun onUserLocation(loc: LatLng)`. Location is fed IN (not a VM dependency) so the VM stays device-free and testable.

- [ ] **Step 1: Write the failing test**

```kotlin
package org.hitchwiki.maps.ui.map
import org.hitchwiki.maps.data.*
import org.hitchwiki.maps.geo.LatLng
import org.hitchwiki.maps.model.*
import io.ktor.client.engine.mock.*
import io.ktor.http.*
import kotlinx.coroutines.test.*
import kotlin.test.*

class MapViewModelTest {
    private fun repoReturning(body: String) = SpotRepository(
        HitchwikiApi(defaultHttpClient(MockEngine {
            respond(body, HttpStatusCode.OK, headersOf(HttpHeaders.ContentType, "application/json"))
        }), "https://example.test"),
        object : SpotCache { // trivial no-op cache; network path is what we exercise
            override suspend fun saveSpots(spots: List<Spot>) {}
            override suspend fun loadSpots(): List<Spot> = emptyList()
        }
    )
    private class FakeDetails(val detail: SpotDetail) : SpotDetailSource {
        var requested: String? = null
        override suspend fun detail(sid: String): SpotDetail { requested = sid; return detail }
    }

    @Test fun loadPopulatesSpotsAndGeoJson() = runTest {
        val vm = MapViewModel(
            repoReturning("""[{"lat":1.0,"lon":2.0,"rating":4.0,"review_count":3}]"""),
            FakeDetails(SpotDetail()), this)
        vm.load(); advanceUntilIdle()
        val s = vm.state.value
        assertFalse(s.loading); assertEquals(1, s.spots.size)
        assertTrue(s.geoJson.contains("\"FeatureCollection\""))
        assertNull(s.error)
    }
    @Test fun selectSpotLoadsDetail() = runTest {
        val det = SpotDetail(spot = SpotInfo(wait = 12), rides = emptyList())
        val fake = FakeDetails(det)
        val vm = MapViewModel(repoReturning("""[]"""), fake, this)
        vm.selectSpot("1.00000_2.00000"); advanceUntilIdle()
        val s = vm.state.value
        assertEquals("1.00000_2.00000", s.selectedSid)
        assertEquals("1.00000_2.00000", fake.requested)
        assertEquals(12, s.selectedDetail?.spot?.wait)
        assertFalse(s.detailLoading)
    }
    @Test fun clearSelectionResetsDetail() = runTest {
        val vm = MapViewModel(repoReturning("""[]"""), FakeDetails(SpotDetail()), this)
        vm.selectSpot("x"); advanceUntilIdle()
        vm.clearSelection()
        assertNull(vm.state.value.selectedSid); assertNull(vm.state.value.selectedDetail)
    }
    @Test fun onUserLocationSetsCameraAndLocation() = runTest {
        val vm = MapViewModel(repoReturning("""[]"""), FakeDetails(SpotDetail()), this)
        vm.onUserLocation(LatLng(48.0, 11.0))
        assertEquals(LatLng(48.0, 11.0), vm.state.value.userLocation)
        assertEquals(LatLng(48.0, 11.0), vm.state.value.cameraTarget)
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mobile && ./gradlew :composeApp:testDebugUnitTest --tests "org.hitchwiki.maps.ui.map.MapViewModelTest"`
Expected: FAIL — `MapViewModel`/`MapUiState`/`SpotDetailSource` unresolved.

- [ ] **Step 3: Implement**

`data/SpotDetailSource.kt`:
```kotlin
package org.hitchwiki.maps.data
import org.hitchwiki.maps.model.SpotDetail

/** Seam for fetching one spot's detail, so the map view-model is testable with a fake. */
interface SpotDetailSource { suspend fun detail(sid: String): SpotDetail }

class ApiSpotDetailSource(private val api: HitchwikiApi) : SpotDetailSource {
    override suspend fun detail(sid: String): SpotDetail = api.spotDetail(sid)
}
```

`ui/map/MapUiState.kt`:
```kotlin
package org.hitchwiki.maps.ui.map
import org.hitchwiki.maps.geo.LatLng
import org.hitchwiki.maps.model.Spot
import org.hitchwiki.maps.model.SpotDetail

data class MapUiState(
    val loading: Boolean = false,
    val spots: List<Spot> = emptyList(),
    val geoJson: String = """{"type":"FeatureCollection","features":[]}""",
    val error: String? = null,
    val selectedSid: String? = null,
    val selectedDetail: SpotDetail? = null,
    val detailLoading: Boolean = false,
    val userLocation: LatLng? = null,
    // Non-null when the map should animate to a new center; the map clears it after consuming.
    val cameraTarget: LatLng? = null,
)
```

`ui/map/MapViewModel.kt`:
```kotlin
package org.hitchwiki.maps.ui.map
import org.hitchwiki.maps.data.SpotDetailSource
import org.hitchwiki.maps.data.SpotRepository
import org.hitchwiki.maps.data.buildSpotsGeoJson
import org.hitchwiki.maps.geo.LatLng
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

class MapViewModel(
    private val spots: SpotRepository,
    private val details: SpotDetailSource,
    private val scope: CoroutineScope,
) {
    private val _state = MutableStateFlow(MapUiState())
    val state: StateFlow<MapUiState> = _state.asStateFlow()

    fun load() {
        _state.update { it.copy(loading = true, error = null) }
        scope.launch {
            try {
                val fresh = spots.spots()
                _state.update { it.copy(loading = false, spots = fresh, geoJson = buildSpotsGeoJson(fresh)) }
            } catch (e: Throwable) {
                _state.update { it.copy(loading = false, error = e.message ?: "Failed to load spots") }
            }
        }
    }

    fun selectSpot(sid: String) {
        _state.update { it.copy(selectedSid = sid, selectedDetail = null, detailLoading = true) }
        scope.launch {
            try {
                val d = details.detail(sid)
                // Ignore a late result if the user already selected/closed another spot.
                _state.update { if (it.selectedSid == sid) it.copy(selectedDetail = d, detailLoading = false) else it }
            } catch (e: Throwable) {
                _state.update { if (it.selectedSid == sid) it.copy(detailLoading = false) else it }
            }
        }
    }

    fun clearSelection() =
        _state.update { it.copy(selectedSid = null, selectedDetail = null, detailLoading = false) }

    fun onUserLocation(loc: LatLng) =
        _state.update { it.copy(userLocation = loc, cameraTarget = loc) }

    fun cameraConsumed() = _state.update { it.copy(cameraTarget = null) }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd mobile && ./gradlew :composeApp:testDebugUnitTest --tests "org.hitchwiki.maps.ui.map.MapViewModelTest"`
Expected: PASS (4 tests).

- [ ] **Step 5: Run full suite, then commit**

Run: `cd mobile && ./gradlew :composeApp:testDebugUnitTest`
Expected: PASS (all prior + new).
```bash
git add mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/data/SpotDetailSource.kt \
        mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/ui/map/MapUiState.kt \
        mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/ui/map/MapViewModel.kt \
        mobile/composeApp/src/commonTest/kotlin/org/hitchwiki/maps/ui/map/MapViewModelTest.kt
git commit -m "feat(mobile): MapViewModel state machine + SpotDetailSource seam"
```

---

## Task 3: Map seam contracts + `expect` declarations + stub actuals (all targets compile)

An `expect` needs an `actual` on **every** target to compile. This task declares the seam and provides a **stub** actual for both Android and iOS, so the project keeps building; Task 5/6 replace the Android stubs with the real MapLibre/location code.

**Files:**
- Create: `mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/map/MapContracts.kt`
- Create: `mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/map/PlatformMap.kt`
- Create: `mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/location/LocationProvider.kt`
- Create: `mobile/composeApp/src/androidMain/kotlin/org/hitchwiki/maps/map/PlatformMap.android.kt` (stub)
- Create: `mobile/composeApp/src/androidMain/kotlin/org/hitchwiki/maps/location/LocationProvider.android.kt` (stub)
- Create: `mobile/composeApp/src/iosMain/kotlin/org/hitchwiki/maps/map/PlatformMap.ios.kt` (stub)
- Create: `mobile/composeApp/src/iosMain/kotlin/org/hitchwiki/maps/location/LocationProvider.ios.kt` (stub)

**Interfaces:**
- Produces:
  - `data class MapState(val geoJson: String, val cameraTarget: LatLng?)`; `class MapCallbacks(val onSpotClick: (String) -> Unit, val onCameraConsumed: () -> Unit)`.
  - `@Composable expect fun PlatformMap(state: MapState, callbacks: MapCallbacks, modifier: Modifier)`.
  - `expect class LocationProvider { suspend fun current(): LatLng? }`. (Android actual gets a `Context` via its own constructor; the expect declares no constructor.)

- [ ] **Step 1: Common contracts + expects**

`map/MapContracts.kt`:
```kotlin
package org.hitchwiki.maps.map
import org.hitchwiki.maps.geo.LatLng

/** Everything the platform map needs to render, as platform-neutral data. */
data class MapState(val geoJson: String, val cameraTarget: LatLng?)

/** Callbacks from the platform map back into shared code. */
class MapCallbacks(
    val onSpotClick: (sid: String) -> Unit,
    val onCameraConsumed: () -> Unit,
)
```

`map/PlatformMap.kt`:
```kotlin
package org.hitchwiki.maps.map
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier

/** The platform map surface. Android renders MapLibre; iOS is a stub for now. */
@Composable
expect fun PlatformMap(state: MapState, callbacks: MapCallbacks, modifier: Modifier)
```

`location/LocationProvider.kt`:
```kotlin
package org.hitchwiki.maps.location
import org.hitchwiki.maps.geo.LatLng

/** Last-known device location, or null if unavailable/denied. */
expect class LocationProvider {
    suspend fun current(): LatLng?
}
```

- [ ] **Step 2: Stub actuals**

`androidMain/.../map/PlatformMap.android.kt` (stub — replaced in Task 5):
```kotlin
package org.hitchwiki.maps.map
import androidx.compose.foundation.layout.Box
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier

@Composable
actual fun PlatformMap(state: MapState, callbacks: MapCallbacks, modifier: Modifier) {
    // TODO(Task 5): real MapLibre map. Stub so the project compiles.
    Box(modifier)
}
```

`androidMain/.../location/LocationProvider.android.kt` (stub — replaced in Task 6):
```kotlin
package org.hitchwiki.maps.location
import org.hitchwiki.maps.geo.LatLng

actual class LocationProvider {
    actual suspend fun current(): LatLng? = null // TODO(Task 6): fused/last-known location
}
```

`iosMain/.../map/PlatformMap.ios.kt`:
```kotlin
package org.hitchwiki.maps.map
import androidx.compose.foundation.layout.Box
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier

@Composable
actual fun PlatformMap(state: MapState, callbacks: MapCallbacks, modifier: Modifier) {
    // TODO(iOS bring-up): MapLibre iOS actual.
    Box(modifier)
}
```

`iosMain/.../location/LocationProvider.ios.kt`:
```kotlin
package org.hitchwiki.maps.location
import org.hitchwiki.maps.geo.LatLng

actual class LocationProvider {
    actual suspend fun current(): LatLng? = null
}
```

- [ ] **Step 3: Build both targets**

Run: `cd mobile && ./gradlew :composeApp:assembleDebug :composeApp:compileKotlinIosSimulatorArm64`
Expected: BUILD SUCCESSFUL (both targets compile with stubs).

- [ ] **Step 4: Commit**

```bash
git add mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/map \
        mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/location \
        mobile/composeApp/src/androidMain/kotlin/org/hitchwiki/maps/map \
        mobile/composeApp/src/androidMain/kotlin/org/hitchwiki/maps/location \
        mobile/composeApp/src/iosMain/kotlin/org/hitchwiki/maps/map \
        mobile/composeApp/src/iosMain/kotlin/org/hitchwiki/maps/location
git commit -m "feat(mobile): map/location expect-actual seam with stub actuals"
```

---

## Task 4: `MapScreen` composable — wire ViewModel to PlatformMap + overlay

**Files:**
- Create: `mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/ui/map/MapScreen.kt`

**Interfaces:**
- Consumes: `MapViewModel` (Task 2), `PlatformMap`/`MapState`/`MapCallbacks` (Task 3), `LatLng`.
- Produces: `@Composable fun MapScreen(viewModel: MapViewModel, onRequestLocation: () -> Unit, modifier: Modifier = Modifier)`. `onRequestLocation` is invoked when the location FAB is tapped; the platform host wires it to permission + `LocationProvider` and calls `viewModel.onUserLocation(...)`.

- [ ] **Step 1: Implement (built, then compile-verified — no unit test; this is Compose UI)**

```kotlin
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
```

- [ ] **Step 2: Build (uses the stub PlatformMap for now)**

Run: `cd mobile && ./gradlew :composeApp:assembleDebug :composeApp:compileKotlinIosSimulatorArm64`
Expected: BUILD SUCCESSFUL.

- [ ] **Step 3: Commit**

```bash
git add mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/ui/map/MapScreen.kt
git commit -m "feat(mobile): MapScreen composable wiring ViewModel to map + overlay"
```

---

## Task 5: Android `PlatformMap` actual — MapLibre map, OSM US basemap, clustered markers, tap

This is the highest-risk task. The code below targets `org.maplibre.gl:android-sdk:11.5.0`. The MapLibre expression/layer API is version-sensitive; if a symbol/signature differs in the resolved SDK, adapt it to the 11.5.0 API (do NOT change the SDK version) and record the adjustment in your report — like a transcription fix, not a redesign. Acceptance is `assembleDebug` green; visual correctness is user-verified later.

**Files:**
- Modify: `mobile/gradle/libs.versions.toml` — add MapLibre (from the P1 spike).
- Modify: `mobile/composeApp/build.gradle.kts` — `androidMain` dep `implementation(libs.maplibre.android)`.
- Create: `mobile/composeApp/src/androidMain/assets/osm_us_style.json` — bundled label-free style.
- Replace: `mobile/composeApp/src/androidMain/kotlin/org/hitchwiki/maps/map/PlatformMap.android.kt`.

**Interfaces:**
- Consumes: `MapState`/`MapCallbacks` (Task 3), OSM US TileJSON.
- Produces: a working Android `PlatformMap` actual. Feature property `sid` is read on tap and passed to `onSpotClick`.

- [ ] **Step 1: Add the MapLibre dependency**

In `libs.versions.toml`: `[versions]` add `maplibre-android = "11.5.0"`; `[libraries]` add
`maplibre-android = { module = "org.maplibre.gl:android-sdk", version.ref = "maplibre-android" }`.
In `composeApp/build.gradle.kts`, `androidMain.dependencies { ... }`: add `implementation(libs.maplibre.android)`.

- [ ] **Step 2: Bundle the label-free OSM US style**

Create `mobile/composeApp/src/androidMain/assets/osm_us_style.json` — a minimal OpenMapTiles-schema style with NO symbol/text layers (so no glyphs needed), sourcing the OSM US TileJSON:
```json
{
  "version": 8,
  "name": "OSM US label-free",
  "sources": {
    "openmaptiles": { "type": "vector", "url": "https://tiles.openstreetmap.us/vector/openmaptiles.json" }
  },
  "layers": [
    { "id": "background", "type": "background", "paint": { "background-color": "#f8f4f0" } },
    { "id": "water", "type": "fill", "source": "openmaptiles", "source-layer": "water",
      "paint": { "fill-color": "#a0c8f0" } },
    { "id": "landcover", "type": "fill", "source": "openmaptiles", "source-layer": "landcover",
      "paint": { "fill-color": "#d8e8c8", "fill-opacity": 0.6 } },
    { "id": "landuse", "type": "fill", "source": "openmaptiles", "source-layer": "landuse",
      "paint": { "fill-color": "#e8e0d8", "fill-opacity": 0.5 } },
    { "id": "waterway", "type": "line", "source": "openmaptiles", "source-layer": "waterway",
      "paint": { "line-color": "#a0c8f0" } },
    { "id": "roads", "type": "line", "source": "openmaptiles", "source-layer": "transportation",
      "paint": { "line-color": "#ffffff", "line-width": 1.2 } },
    { "id": "boundary", "type": "line", "source": "openmaptiles", "source-layer": "boundary",
      "filter": ["<=", "admin_level", 2],
      "paint": { "line-color": "#9e9cab", "line-dasharray": [3, 1], "line-width": 1 } },
    { "id": "building", "type": "fill", "source": "openmaptiles", "source-layer": "building",
      "paint": { "fill-color": "#e0dcd4" } }
  ]
}
```
Load it in code via `asset://osm_us_style.json`.

- [ ] **Step 3: Implement the Android actual**

Replace `PlatformMap.android.kt`:
```kotlin
package org.hitchwiki.maps.map
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.ui.Modifier
import androidx.compose.ui.viewinterop.AndroidView
import org.hitchwiki.maps.geo.LatLng
import org.maplibre.android.MapLibre
import org.maplibre.android.camera.CameraUpdateFactory
import org.maplibre.android.geometry.LatLng as MlLatLng
import org.maplibre.android.maps.MapView
import org.maplibre.android.maps.MapLibreMap
import org.maplibre.android.maps.Style
import org.maplibre.android.style.expressions.Expression
import org.maplibre.android.style.layers.CircleLayer
import org.maplibre.android.style.layers.PropertyFactory
import org.maplibre.android.style.sources.GeoJsonOptions
import org.maplibre.android.style.sources.GeoJsonSource

private const val SRC = "spots"
private const val LYR_CLUSTER = "spots-clusters"
private const val LYR_POINT = "spots-points"

@Composable
actual fun PlatformMap(state: MapState, callbacks: MapCallbacks, modifier: Modifier) {
    AndroidView(
        modifier = modifier,
        factory = { ctx ->
            MapLibre.getInstance(ctx)
            MapView(ctx).apply {
                getMapAsync { map ->
                    map.setStyle(Style.Builder().fromUri("asset://osm_us_style.json")) { style ->
                        val source = GeoJsonSource(
                            SRC, state.geoJson,
                            GeoJsonOptions().withCluster(true).withClusterMaxZoom(13).withClusterRadius(50),
                        )
                        style.addSource(source)

                        // Cluster circles: sized by point_count (no text -> no glyphs).
                        style.addLayer(CircleLayer(LYR_CLUSTER, SRC).apply {
                            setFilter(Expression.has("point_count"))
                            setProperties(
                                PropertyFactory.circleColor(android.graphics.Color.parseColor("#4464ad")),
                                PropertyFactory.circleRadius(
                                    Expression.step(Expression.get("point_count"),
                                        Expression.literal(14f),
                                        Expression.stop(50, 20f), Expression.stop(500, 28f))),
                                PropertyFactory.circleOpacity(0.85f),
                            )
                        })

                        // Unclustered points: colored by rating.
                        style.addLayer(CircleLayer(LYR_POINT, SRC).apply {
                            setFilter(Expression.not(Expression.has("point_count")))
                            setProperties(
                                PropertyFactory.circleRadius(6f),
                                PropertyFactory.circleStrokeWidth(1f),
                                PropertyFactory.circleStrokeColor(android.graphics.Color.WHITE),
                                PropertyFactory.circleColor(
                                    Expression.step(Expression.get("rating"),
                                        Expression.literal("#c62828"),      // < 3
                                        Expression.stop(3, "#f9a825"),       // == 3
                                        Expression.stop(4, "#2e7d32"))),     // >= 4
                            )
                        })

                        map.addOnMapClickListener { point ->
                            val screen = map.projection.toScreenLocation(point)
                            val hits = map.queryRenderedFeatures(screen, LYR_POINT)
                            val sid = hits.firstOrNull()?.getStringProperty("sid")
                            if (sid != null) { callbacks.onSpotClick(sid); return@addOnMapClickListener true }
                            // Tapped a cluster? zoom in one step to expand it.
                            val clusterHit = map.queryRenderedFeatures(screen, LYR_CLUSTER).isNotEmpty()
                            if (clusterHit) {
                                map.animateCamera(CameraUpdateFactory.zoomBy(2.0, screen)); true
                            } else false
                        }
                    }
                }
            }
        },
        update = { view ->
            // On recomposition, push the latest GeoJSON to the existing source and consume any
            // pending camera target. getMapAsync runs the callback immediately if the map is
            // already ready, so this does not re-init the map or re-add layers/listeners.
            view.getMapAsync { m ->
                m.style?.getSourceAs<GeoJsonSource>(SRC)?.setGeoJson(state.geoJson)
                state.cameraTarget?.let {
                    m.animateCamera(CameraUpdateFactory.newLatLngZoom(MlLatLng(it.lat, it.lon), 12.0))
                    callbacks.onCameraConsumed()
                }
            }
        },
    )
}
```
Note: `MapView` needs lifecycle calls (`onStart/onResume/onPause/onStop/onDestroy/onLowMemory`) to render reliably. Wire them via a `DisposableEffect` + the Compose `LifecycleOwner`, or call `onStart()`/`onResume()` in `factory` and `onStop()`/`onDestroy()` in `AndroidView`'s `onRelease`. Implement the minimal lifecycle needed for the map to display and not leak; record what you wired in your report. If the `update` block's async `getMapAsync` double-registers click listeners or causes flicker, hold the ready `MapLibreMap` from `factory` in a `remember { mutableStateOf<MapLibreMap?>(null) }` (or the `MapView` via `view.tag`) and update the source directly in `update` instead of calling `getMapAsync` again — fix to whatever renders correctly and report it.

- [ ] **Step 4: Build**

Run: `cd mobile && ./gradlew :composeApp:assembleDebug`
Expected: BUILD SUCCESSFUL, APK produced. If a MapLibre API symbol differs at 11.5.0 (expression factory, `getSourceAs`, `queryRenderedFeatures` overload), adapt to the resolved API and note it.

- [ ] **Step 5: iOS compile guard + commit**

Run: `cd mobile && ./gradlew :composeApp:compileKotlinIosSimulatorArm64`
Expected: BUILD SUCCESSFUL (iOS stub unaffected).
```bash
git add mobile/gradle/libs.versions.toml mobile/composeApp/build.gradle.kts \
        mobile/composeApp/src/androidMain/assets/osm_us_style.json \
        mobile/composeApp/src/androidMain/kotlin/org/hitchwiki/maps/map/PlatformMap.android.kt
git commit -m "feat(mobile): Android MapLibre map with OSM US basemap + clustered rating markers"
```

---

## Task 6: Android `LocationProvider` actual + permissions

**Files:**
- Modify: `mobile/composeApp/src/androidMain/AndroidManifest.xml` — add `INTERNET` (if not present) + `ACCESS_FINE_LOCATION` + `ACCESS_COARSE_LOCATION`.
- Modify: `mobile/gradle/libs.versions.toml` + `composeApp/build.gradle.kts` — add `play-services-location` to `androidMain`.
- Replace: `mobile/composeApp/src/androidMain/kotlin/org/hitchwiki/maps/location/LocationProvider.android.kt`.

**Interfaces:**
- Produces: `actual class LocationProvider(context: Context)` whose `current()` returns last-known location or null. (The `expect` declares no constructor, so the Android actual's `Context` constructor is supplied by the host in Task 7.)

- [ ] **Step 1: Manifest permissions**

In `AndroidManifest.xml`, inside `<manifest>` before `<application>`:
```xml
<uses-permission android:name="android.permission.INTERNET"/>
<uses-permission android:name="android.permission.ACCESS_COARSE_LOCATION"/>
<uses-permission android:name="android.permission.ACCESS_FINE_LOCATION"/>
```

- [ ] **Step 2: Dependency**

`libs.versions.toml`: `[versions]` add `play-services-location = "21.3.0"`; `[libraries]` add
`play-services-location = { module = "com.google.android.gms:play-services-location", version.ref = "play-services-location" }`.
`composeApp/build.gradle.kts` `androidMain.dependencies`: `implementation(libs.play.services.location)`.

- [ ] **Step 3: Implement**

```kotlin
package org.hitchwiki.maps.location
import android.annotation.SuppressLint
import android.content.Context
import com.google.android.gms.location.LocationServices
import kotlinx.coroutines.suspendCancellableCoroutine
import org.hitchwiki.maps.geo.LatLng
import kotlin.coroutines.resume

actual class LocationProvider(private val context: Context) {
    // Caller (Task 7) requests permission before invoking; annotate to satisfy lint.
    @SuppressLint("MissingPermission")
    actual suspend fun current(): LatLng? = suspendCancellableCoroutine { cont ->
        val client = LocationServices.getFusedLocationProviderClient(context)
        client.lastLocation
            .addOnSuccessListener { loc -> cont.resume(loc?.let { LatLng(it.latitude, it.longitude) }) }
            .addOnFailureListener { cont.resume(null) }
    }
}
```

- [ ] **Step 4: Build + iOS compile guard + commit**

Run: `cd mobile && ./gradlew :composeApp:assembleDebug :composeApp:compileKotlinIosSimulatorArm64`
Expected: BUILD SUCCESSFUL.
```bash
git add mobile/composeApp/src/androidMain/AndroidManifest.xml mobile/gradle/libs.versions.toml \
        mobile/composeApp/build.gradle.kts \
        mobile/composeApp/src/androidMain/kotlin/org/hitchwiki/maps/location/LocationProvider.android.kt
git commit -m "feat(mobile): Android last-known LocationProvider + location permissions"
```

---

## Task 7: `MainActivity` wiring — build the dependency graph and host `MapScreen`

**Files:**
- Replace: `mobile/composeApp/src/androidMain/kotlin/org/hitchwiki/maps/MainActivity.kt`.

**Interfaces:**
- Consumes: everything above + P1 (`DatabaseDriverFactory`, `HitchwikiDb`, `SqlDelightSpotCache`, `defaultHttpClient`, `HitchwikiApi`, `SpotRepository`, `ApiSpotDetailSource`), `MapViewModel`, `MapScreen`, `LocationProvider`.
- Produces: the running app — `MainActivity` builds the graph and shows the map; the location FAB requests permission then feeds the location to the ViewModel.

- [ ] **Step 1: Implement**

```kotlin
package org.hitchwiki.maps
import android.Manifest
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.material3.MaterialTheme
import androidx.lifecycle.lifecycleScope
import io.ktor.client.engine.okhttp.OkHttp
import kotlinx.coroutines.launch
import org.hitchwiki.maps.data.*
import org.hitchwiki.maps.db.HitchwikiDb
import org.hitchwiki.maps.location.LocationProvider
import org.hitchwiki.maps.ui.map.MapScreen
import org.hitchwiki.maps.ui.map.MapViewModel

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Build the P1 data graph. DatabaseDriverFactory's Android actual takes a Context.
        val db = HitchwikiDb(DatabaseDriverFactory(applicationContext).create())
        val api = HitchwikiApi(defaultHttpClient(OkHttp.create()))
        val repository = SpotRepository(api, SqlDelightSpotCache(db))
        val details = ApiSpotDetailSource(api)
        val viewModel = MapViewModel(repository, details, lifecycleScope)
        val locationProvider = LocationProvider(applicationContext)

        val permissionLauncher = registerForActivityResult(
            ActivityResultContracts.RequestPermission()
        ) { granted ->
            if (granted) lifecycleScope.launch {
                locationProvider.current()?.let { viewModel.onUserLocation(it) }
            }
        }

        setContent {
            MaterialTheme {
                MapScreen(
                    viewModel = viewModel,
                    onRequestLocation = { permissionLauncher.launch(Manifest.permission.ACCESS_FINE_LOCATION) },
                )
            }
        }
    }
}
```
Note: `DatabaseDriverFactory`'s Android actual currently takes a `Context` (P1 Task 8). If its constructor differs, adapt this call to the real signature and report it. If `HitchwikiDb`'s constructor/driver wiring differs from P1, match P1's actual API.

- [ ] **Step 2: Build**

Run: `cd mobile && ./gradlew :composeApp:assembleDebug`
Expected: BUILD SUCCESSFUL, APK at `composeApp/build/outputs/apk/debug/`.

- [ ] **Step 3: Full suite + iOS compile guard**

Run: `cd mobile && ./gradlew :composeApp:testDebugUnitTest :composeApp:compileKotlinIosSimulatorArm64`
Expected: BUILD SUCCESSFUL — all shared unit tests pass and iOS compiles.

- [ ] **Step 4: Write the manual test steps (for the human) into the report**

The agent cannot run an emulator. In your report, give the exact commands the human runs:
```
# with an AVD running (e.g. Pixel7_API35):
cd mobile && ./gradlew :composeApp:installDebug
~/Library/Android/sdk/platform-tools/adb shell monkey -p org.hitchwiki.maps 1
```
Expected on screen: the OSM US basemap renders; spots appear as clustered blue circles that split into rating-colored dots as you zoom in; tapping a dot opens a bottom sheet with wait/ride info; the ◎ button (after granting permission) recenters on the device location.

- [ ] **Step 5: Commit**

```bash
git add mobile/composeApp/src/androidMain/kotlin/org/hitchwiki/maps/MainActivity.kt
git commit -m "feat(mobile): host MapScreen from MainActivity with live data + location"
```

---

## Self-Review

**Spec coverage:**
- OSM US vector basemap (no key) — Task 5 (style asset + TileJSON) ✓.
- All live spots as clustered markers — Tasks 1 (GeoJSON) + 5 (cluster source/layers) ✓.
- Rating-colored markers — Task 5 (green/amber/red step expression) ✓.
- Tap → load SpotDetail → minimal summary — Tasks 2 (VM), 4 (bottom sheet), 5 (tap→sid) ✓.
- Current-location + camera — Tasks 2 (onUserLocation/cameraTarget), 6 (provider+perms), 7 (FAB→permission→provider) ✓.
- Attribution — Task 4 ✓.
- expect/actual seam, MapLibre out of commonMain — Tasks 3/5; verified by common tests compiling without MapLibre ✓.
- Android-only, iOS compiles — stub actuals (Task 3) + iOS compile guard in Tasks 3–7 ✓.
- CircleLayers only / no glyphs — Task 5 style + layers (no SymbolLayer) ✓.
- Deferred correctly absent: offline/PMTiles, full sheet, filters/search, iOS map, cluster-count text/place labels.

**Placeholder scan:** No "TBD"/"handle later". The version-sensitive MapLibre API (Task 5) and the P1 constructor signatures (Task 7) are handled with explicit "adapt to the resolved API and report the adjustment" instructions — the same transcription-fix pattern P1 used for Ktor, not open-ended placeholders. The MapView lifecycle wiring (Task 5) names exactly which callbacks to wire and why.

**Type consistency:** `LatLng` (common), `MapState`/`MapCallbacks`, `MapViewModel` (`load`/`selectSpot`/`clearSelection`/`onUserLocation`/`cameraConsumed`), `SpotDetailSource.detail`, `buildSpotsGeoJson`, `PlatformMap(state, callbacks, modifier)`, `LocationProvider.current()` — names are consistent across every task that references them. P1 symbols (`SpotRepository.spots`, `HitchwikiApi.spotDetail`, `DatabaseDriverFactory`, `SqlDelightSpotCache`, `defaultHttpClient`, `spotId`, `appJson`) are consumed as they exist.

**Risk notes carried:** Task 5 is the integration risk (MapLibre clustering/tap/lifecycle at 11.5.0) — complete code provided, `assembleDebug` gate, adapt-and-report for API drift, and a final human render check in Task 7.

---

## Notes for later phases
- **P3:** full spot-detail sheet, filters/search, cluster-count numbers + place-name labels (adds a glyphs URL — confirm the OSM US fonts endpoint), richer basemap style.
- **P6:** offline PMTiles + region download; the map source swaps from the TileJSON to a local PMTiles.
- **iOS bring-up:** real MapLibre iOS `actual` for `PlatformMap` + a CoreLocation `LocationProvider`.
- **Production tiles:** move off the OSM US starter tier (Partner tier donation or self-host) before a public launch.
