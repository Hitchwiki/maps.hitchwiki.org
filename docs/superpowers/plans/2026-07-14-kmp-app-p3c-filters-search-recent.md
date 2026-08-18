# KMP App P3c — Filters, Search & Recent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add map filters and a search/recent-rides screen to the Android KMP app, completing the P3 UI milestone.

**Architecture:** Filters run over the in-memory `Spot` list and rebuild the clustered GeoJSON source off-main (so cluster counts stay correct); a targeted `buildSpotsGeoJson` rewrite makes that rebuild fast. Search/Recent share one lazily-loaded file (`spots_recent.json`, latest 1000 rides); tapping a result flies the map to the spot. All new code is commonMain Compose/data; only `PlatformMap` stays a stub for iOS.

**Tech Stack:** Kotlin Multiplatform, Compose Multiplatform, kotlinx-serialization, kotlinx-coroutines, JetBrains Compose Navigation, Ktor (MockEngine for tests).

**Spec:** `docs/superpowers/specs/2026-07-14-kmp-app-p3c-filters-search-recent-design.md`

## Global Constraints

- **Android is the run/test target; iOS stays a compiling stub.** MapLibre lives only in `androidMain`. All new code in this plan is commonMain.
- **Build discipline (memory-constrained host):** each task runs `:composeApp:assembleDebug` and/or `:composeApp:testDebugUnitTest` ONLY. The single iOS guard `:composeApp:compileKotlinIosSimulatorArm64` runs ONCE at the end (Task 8). `gradle.properties` caps daemons to 1G / parallel off — do not change it.
- **Strict JSON:** models are parsed with `appJson` (`ignoreUnknownKeys = true`, NOT lenient). Field types must match the backend exactly.
- **Plain-class ViewModels** (not `androidx.lifecycle.ViewModel`): constructor takes its data source(s), a `CoroutineScope`, and — where it does heavy/async work — an injected `workDispatcher: CoroutineDispatcher = Dispatchers.Default` so tests pass `StandardTestDispatcher(testScheduler)` and `advanceUntilIdle()` stays deterministic.
- **Spot id** is `util.spotId(lat, lon)` = `lat.toFixed(5)_lon.toFixed(5)`. The per-spot detail filename and marker `sid` use it.
- **Filter mechanism is rebuild, not layer-filter** — the source is clustered, so filtering must rebuild the source from the filtered subset.
- Work stays LOCAL on branch `feature/kmp-mobile-app`; do not push.

---

### Task 1: Fast `buildSpotsGeoJson` (StringBuilder)

Rewrite the GeoJSON builder from the kotlinx JSON DSL (~12 s for 35 k features) to direct `StringBuilder` output (sub-second), so filter rebuilds are interactive. Same output shape: a FeatureCollection of `Point` features at `[lon, lat]` with `sid` + `rating` properties.

**Files:**
- Modify: `mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/data/GeoJson.kt`
- Test: `mobile/composeApp/src/commonTest/kotlin/org/hitchwiki/maps/data/GeoJsonTest.kt` (create if absent, else add these tests)

**Interfaces:**
- Consumes: `org.hitchwiki.maps.model.Spot`, `org.hitchwiki.maps.util.spotId`.
- Produces: `fun buildSpotsGeoJson(spots: List<Spot>): String` (unchanged signature).

- [ ] **Step 1: Write the failing tests**

Create `GeoJsonTest.kt`:
```kotlin
package org.hitchwiki.maps.data
import org.hitchwiki.maps.model.Spot
import kotlinx.serialization.json.*
import kotlin.test.*

class GeoJsonTest {
    private fun spot(lat: Double, lon: Double, rating: Double) =
        Spot(lat = lat, lon = lon, rating = rating, reviewCount = 1)

    @Test fun emptyListIsEmptyCollection() {
        assertEquals("""{"type":"FeatureCollection","features":[]}""", buildSpotsGeoJson(emptyList()))
    }

    @Test fun buildsPointFeatureWithSidAndRating() {
        val json = appJson.parseToJsonElement(buildSpotsGeoJson(listOf(spot(51.0817, 13.73629, 4.0)))).jsonObject
        assertEquals("FeatureCollection", json["type"]!!.jsonPrimitive.content)
        val feats = json["features"]!!.jsonArray
        assertEquals(1, feats.size)
        val f = feats[0].jsonObject
        assertEquals("Feature", f["type"]!!.jsonPrimitive.content)
        val coords = f["geometry"]!!.jsonObject["coordinates"]!!.jsonArray
        assertEquals(13.73629, coords[0].jsonPrimitive.double)   // lon first (GeoJSON order)
        assertEquals(51.0817, coords[1].jsonPrimitive.double)
        val props = f["properties"]!!.jsonObject
        assertEquals("51.08170_13.73629", props["sid"]!!.jsonPrimitive.content)
        assertEquals(4.0, props["rating"]!!.jsonPrimitive.double)
    }

    @Test fun featureCountMatchesInputAndIsValidJson() {
        val spots = listOf(spot(1.0, 2.0, 5.0), spot(3.0, 4.0, 3.0), spot(-5.5, 6.25, 1.0))
        val feats = appJson.parseToJsonElement(buildSpotsGeoJson(spots)).jsonObject["features"]!!.jsonArray
        assertEquals(3, feats.size)
        // negative + fractional coordinates round-trip
        val third = feats[2].jsonObject["geometry"]!!.jsonObject["coordinates"]!!.jsonArray
        assertEquals(6.25, third[0].jsonPrimitive.double)
        assertEquals(-5.5, third[1].jsonPrimitive.double)
    }
}
```

- [ ] **Step 2: Run the tests to verify they fail (or pass on the old impl)**

Run: `cd mobile && ./gradlew :composeApp:testDebugUnitTest --tests "*GeoJsonTest"`
Expected: the new file compiles; tests may PASS against the old DSL impl (they assert behavior, not implementation). That is fine — they are the safety net for the rewrite in Step 3.

- [ ] **Step 3: Rewrite `buildSpotsGeoJson` with a StringBuilder**

Replace the body of `GeoJson.kt`:
```kotlin
package org.hitchwiki.maps.data
import org.hitchwiki.maps.model.Spot
import org.hitchwiki.maps.util.spotId

/** Build a GeoJSON FeatureCollection string for MapLibre's clustered GeoJsonSource.
 *  Each spot -> a Point at [lon, lat] (GeoJSON order) with `sid` (tap->detail lookup) and
 *  `rating` (color ramp). Built with a StringBuilder rather than the kotlinx JSON DSL because
 *  the DSL costs ~12 s for 35k features; direct appends are sub-second, which is what makes
 *  interactive filter rebuilds (and a faster cold load) viable. `sid` comes from spotId() and
 *  contains only [0-9 . _ -], so it needs no JSON string escaping. */
fun buildSpotsGeoJson(spots: List<Spot>): String {
    val sb = StringBuilder(spots.size * 96 + 48)
    sb.append("""{"type":"FeatureCollection","features":[""")
    for (i in spots.indices) {
        val s = spots[i]
        if (i > 0) sb.append(',')
        sb.append("""{"type":"Feature","geometry":{"type":"Point","coordinates":[""")
        sb.append(s.lon).append(',').append(s.lat)
        sb.append("""]},"properties":{"sid":"""").append(spotId(s.lat, s.lon))
        sb.append("""","rating":""").append(s.rating).append("}}")
    }
    sb.append("]}")
    return sb.toString()
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd mobile && ./gradlew :composeApp:testDebugUnitTest --tests "*GeoJsonTest"`
Expected: PASS (all three).

- [ ] **Step 5: Commit**

```bash
git add mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/data/GeoJson.kt \
        mobile/composeApp/src/commonTest/kotlin/org/hitchwiki/maps/data/GeoJsonTest.kt
git commit -m "perf(mobile): build spots GeoJSON via StringBuilder (12s -> sub-second)"
```

---

### Task 2: `FilterState` + `applyFilters`

A pure, testable filter model over `Spot`.

**Files:**
- Create: `mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/ui/map/FilterState.kt`
- Create: `mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/data/SpotFilter.kt`
- Test: `mobile/composeApp/src/commonTest/kotlin/org/hitchwiki/maps/data/SpotFilterTest.kt`

**Interfaces:**
- Consumes: `org.hitchwiki.maps.model.Spot`.
- Produces: `data class FilterState(minRating: Int = 0, osm: Boolean = false, wiki: Boolean = false, cp: Boolean = false, fuel: Boolean = false)` with `val isActive: Boolean`; `fun applyFilters(spots: List<Spot>, f: FilterState): List<Spot>`.

- [ ] **Step 1: Write the failing tests**

```kotlin
package org.hitchwiki.maps.data
import org.hitchwiki.maps.model.Spot
import org.hitchwiki.maps.ui.map.FilterState
import kotlin.test.*

class SpotFilterTest {
    private fun spot(rating: Double, osm: Boolean = false, wiki: Boolean = false,
                     cp: Boolean = false, fuel: Boolean = false) =
        Spot(lat = 1.0, lon = 2.0, rating = rating, reviewCount = 1,
             osm = osm, wiki = wiki, cp = cp, fuel = fuel)

    @Test fun inactiveFilterReturnsAll() {
        val spots = listOf(spot(1.0), spot(5.0))
        assertFalse(FilterState().isActive)
        assertEquals(spots, applyFilters(spots, FilterState()))
    }
    @Test fun minRatingKeepsAtOrAboveThreshold() {
        val spots = listOf(spot(2.0), spot(3.0), spot(4.0), spot(5.0))
        assertEquals(listOf(4.0, 5.0), applyFilters(spots, FilterState(minRating = 4)).map { it.rating })
    }
    @Test fun eachFlagRequiresPresence() {
        val spots = listOf(spot(5.0, osm = true), spot(5.0, wiki = true), spot(5.0))
        assertEquals(1, applyFilters(spots, FilterState(osm = true)).size)
        assertEquals(1, applyFilters(spots, FilterState(wiki = true)).size)
    }
    @Test fun combinedFlagsAndRatingAreAnded() {
        val spots = listOf(
            spot(5.0, osm = true, cp = true),
            spot(5.0, osm = true),
            spot(3.0, osm = true, cp = true),
        )
        val out = applyFilters(spots, FilterState(minRating = 4, osm = true, cp = true))
        assertEquals(1, out.size)
    }
    @Test fun isActiveDetectsAnyConstraint() {
        assertTrue(FilterState(minRating = 3).isActive)
        assertTrue(FilterState(fuel = true).isActive)
        assertFalse(FilterState().isActive)
    }
}
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd mobile && ./gradlew :composeApp:testDebugUnitTest --tests "*SpotFilterTest"`
Expected: FAIL to compile — `FilterState` / `applyFilters` unresolved.

- [ ] **Step 3: Implement**

`FilterState.kt`:
```kotlin
package org.hitchwiki.maps.ui.map

/** Map-marker filter. minRating 0 == "Any"; flags require the corresponding Spot flag. */
data class FilterState(
    val minRating: Int = 0,
    val osm: Boolean = false,
    val wiki: Boolean = false,
    val cp: Boolean = false,
    val fuel: Boolean = false,
) {
    val isActive: Boolean get() = minRating > 0 || osm || wiki || cp || fuel
}
```

`SpotFilter.kt`:
```kotlin
package org.hitchwiki.maps.data
import org.hitchwiki.maps.model.Spot
import org.hitchwiki.maps.ui.map.FilterState

/** Pure filter over the in-memory spot list. Rating is Double; the threshold is an Int floor. */
fun applyFilters(spots: List<Spot>, f: FilterState): List<Spot> =
    if (!f.isActive) spots
    else spots.filter { s ->
        s.rating >= f.minRating &&
            (!f.osm || s.osm) && (!f.wiki || s.wiki) && (!f.cp || s.cp) && (!f.fuel || s.fuel)
    }
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd mobile && ./gradlew :composeApp:testDebugUnitTest --tests "*SpotFilterTest"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/ui/map/FilterState.kt \
        mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/data/SpotFilter.kt \
        mobile/composeApp/src/commonTest/kotlin/org/hitchwiki/maps/data/SpotFilterTest.kt
git commit -m "feat(mobile): FilterState + pure applyFilters over spots"
```

---

### Task 3: `MapViewModel` — filter state, rebuild, and `focusSpot`

Wire filters into the map: hold `filterState`, rebuild the source from the filtered subset off-main, and add `focusSpot` for search results. `spotsBySid` stays keyed on the FULL set so `focusSpot` works even for a filtered-out spot.

**Files:**
- Modify: `mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/ui/map/MapUiState.kt`
- Modify: `mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/ui/map/MapViewModel.kt`
- Test: `mobile/composeApp/src/commonTest/kotlin/org/hitchwiki/maps/ui/map/MapViewModelFilterTest.kt`

**Interfaces:**
- Consumes: `applyFilters`, `buildSpotsGeoJson`, `FilterState`, existing `workDispatcher`.
- Produces: `MapUiState.filterState: FilterState`; `MapViewModel.setFilter(state: FilterState)`; `MapViewModel.focusSpot(lat: Double, lon: Double, sid: String)`.

- [ ] **Step 1: Write the failing tests**

```kotlin
package org.hitchwiki.maps.ui.map
import org.hitchwiki.maps.data.*
import org.hitchwiki.maps.geo.LatLng
import org.hitchwiki.maps.model.Spot
import io.ktor.client.engine.mock.*
import io.ktor.http.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.test.*
import kotlinx.serialization.json.*
import kotlin.test.*

class MapViewModelFilterTest {
    // Two spots: one 5-star OSM, one 2-star non-OSM.
    private val body = """[{"lat":1.0,"lon":2.0,"rating":5.0,"review_count":1,"osm":true},
                           {"lat":3.0,"lon":4.0,"rating":2.0,"review_count":1}]"""
    private fun repo() = SpotRepository(
        HitchwikiApi(defaultHttpClient(MockEngine(MockEngineConfig().apply {
            addHandler { respond(body, HttpStatusCode.OK, headersOf(HttpHeaders.ContentType, "application/json")) }
            dispatcher = Dispatchers.Unconfined
        })), "https://example.test"),
        object : SpotCache {
            override suspend fun saveSpots(spots: List<Spot>) {}
            override suspend fun loadSpots(): List<Spot> = emptyList()
        }
    )
    private val noDetail = object : SpotDetailSource {
        override suspend fun detail(sid: String) = org.hitchwiki.maps.model.SpotDetail()
    }
    private fun featureCount(geoJson: String) =
        appJson.parseToJsonElement(geoJson).jsonObject["features"]!!.jsonArray.size

    @Test fun setFilterNarrowsGeoJsonToSubset() = runTest {
        val vm = MapViewModel(repo(), noDetail, this, StandardTestDispatcher(testScheduler))
        vm.load(); advanceUntilIdle()
        assertEquals(2, featureCount(vm.state.value.geoJson))
        vm.setFilter(FilterState(minRating = 4)); advanceUntilIdle()
        assertEquals(1, featureCount(vm.state.value.geoJson))
        assertEquals(FilterState(minRating = 4), vm.state.value.filterState)
    }
    @Test fun clearingFilterRestoresAll() = runTest {
        val vm = MapViewModel(repo(), noDetail, this, StandardTestDispatcher(testScheduler))
        vm.load(); advanceUntilIdle()
        vm.setFilter(FilterState(osm = true)); advanceUntilIdle()
        assertEquals(1, featureCount(vm.state.value.geoJson))
        vm.setFilter(FilterState()); advanceUntilIdle()
        assertEquals(2, featureCount(vm.state.value.geoJson))
    }
    @Test fun focusSpotSetsCameraAndSelection() = runTest {
        val vm = MapViewModel(repo(), noDetail, this, StandardTestDispatcher(testScheduler))
        vm.load(); advanceUntilIdle()
        vm.focusSpot(3.0, 4.0, "3.00000_4.00000"); advanceUntilIdle()
        assertEquals(LatLng(3.0, 4.0), vm.state.value.cameraTarget)
        assertEquals("3.00000_4.00000", vm.state.value.selectedSid)
    }
}
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd mobile && ./gradlew :composeApp:testDebugUnitTest --tests "*MapViewModelFilterTest"`
Expected: FAIL to compile — `filterState` / `setFilter` / `focusSpot` unresolved.

- [ ] **Step 3: Add `filterState` to `MapUiState`**

In `MapUiState.kt`, add the field (leave the rest unchanged):
```kotlin
    val filterState: FilterState = FilterState(),
```
(no import needed — `FilterState` is in the same package `org.hitchwiki.maps.ui.map`.)

- [ ] **Step 4: Implement `setFilter` + `focusSpot`, apply filter in `load()`**

In `MapViewModel.kt`, import `applyFilters`:
```kotlin
import org.hitchwiki.maps.data.applyFilters
```
Change the `load()` build line to honor the current filter (default is inactive → all, so the initial view is unchanged):
```kotlin
                    val geo = buildSpotsGeoJson(applyFilters(fresh, _state.value.filterState))
```
Add these methods (e.g. after `load()`):
```kotlin
    /** Re-filter the already-loaded spots and rebuild the clustered source off-main. spotsBySid
     *  stays on the full set, so focusSpot still resolves a currently-filtered-out spot. */
    fun setFilter(state: FilterState) {
        _state.update { it.copy(filterState = state) }
        scope.launch {
            val full = _state.value.spots
            val geo = withContext(workDispatcher) { buildSpotsGeoJson(applyFilters(full, state)) }
            _state.update { it.copy(geoJson = geo) }
        }
    }

    /** Center the map on a spot (from a search/recent result) and open its summary sheet. */
    fun focusSpot(lat: Double, lon: Double, sid: String) {
        _state.update { it.copy(cameraTarget = LatLng(lat, lon)) }
        selectSpot(sid)
    }
```

- [ ] **Step 5: Run to verify it passes (and the existing map tests still pass)**

Run: `cd mobile && ./gradlew :composeApp:testDebugUnitTest --tests "*MapViewModel*"`
Expected: PASS (new filter tests + the existing `MapViewModelTest` / `MapViewModelSelectedTest`).

- [ ] **Step 6: Commit**

```bash
git add mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/ui/map/MapUiState.kt \
        mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/ui/map/MapViewModel.kt \
        mobile/composeApp/src/commonTest/kotlin/org/hitchwiki/maps/ui/map/MapViewModelFilterTest.kt
git commit -m "feat(mobile): MapViewModel filter (rebuild off-main) + focusSpot"
```

---

### Task 4: `RecentRide` model + coordinate parsing

Model `spots_recent.json` and derive `lat`/`lon`/`sid` from the `#<lat>,<lon>` url; a malformed url yields null coordinates (skipped by callers), never a crash.

**Files:**
- Create: `mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/model/RecentRide.kt`
- Test: `mobile/composeApp/src/commonTest/kotlin/org/hitchwiki/maps/model/RecentRideTest.kt`

**Interfaces:**
- Consumes: `org.hitchwiki.maps.util.spotId`.
- Produces: `@Serializable data class RecentRide(url, submissionTime?, hitchhikerName?, rating?, distance?, text?)`; extension `val RecentRide.latLon: Pair<Double, Double>?`; `val RecentRide.sid: String?`.

- [ ] **Step 1: Write the failing tests**

```kotlin
package org.hitchwiki.maps.model
import org.hitchwiki.maps.data.appJson
import kotlin.test.*

class RecentRideTest {
    @Test fun parsesRealRecordShape() {
        val r = appJson.decodeFromString<RecentRide>(
            """{"url":"#52.50374,13.27900","submission_time":"2026-06-29 08:37:21 🕒",
                "hitchhiker_name":"Anonymous","rating":5,"distance":null,"text":"Nice spot"}"""
        )
        assertEquals("Anonymous", r.hitchhikerName)
        assertEquals(5, r.rating)
        assertNull(r.distance)
        assertEquals("Nice spot", r.text)
    }
    @Test fun derivesLatLonAndSidFromUrl() {
        val r = appJson.decodeFromString<RecentRide>("""{"url":"#52.50374,13.27900"}""")
        assertEquals(52.50374 to 13.27900, r.latLon)
        assertEquals("52.50374_13.27900", r.sid)
    }
    @Test fun malformedUrlYieldsNullNotCrash() {
        assertNull(appJson.decodeFromString<RecentRide>("""{"url":"#nope"}""").latLon)
        assertNull(appJson.decodeFromString<RecentRide>("""{"url":""}""").sid)
        assertNull(appJson.decodeFromString<RecentRide>("""{"url":"#1.0,2.0,3.0"}""").latLon)
    }
}
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd mobile && ./gradlew :composeApp:testDebugUnitTest --tests "*RecentRideTest"`
Expected: FAIL to compile — `RecentRide` unresolved.

- [ ] **Step 3: Implement**

```kotlin
package org.hitchwiki.maps.model
import org.hitchwiki.maps.util.spotId
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/** One record of spots_recent.json (latest ~1000 rides). `url` is a "#<lat>,<lon>" fragment. */
@Serializable
data class RecentRide(
    val url: String,
    @SerialName("submission_time") val submissionTime: String? = null,
    @SerialName("hitchhiker_name") val hitchhikerName: String? = null,
    val rating: Int? = null,
    val distance: Double? = null,
    val text: String? = null,
)

/** Parse "#lat,lon" -> (lat, lon); null if the url isn't exactly two parseable numbers. */
val RecentRide.latLon: Pair<Double, Double>?
    get() {
        val parts = url.removePrefix("#").split(",")
        if (parts.size != 2) return null
        val lat = parts[0].toDoubleOrNull() ?: return null
        val lon = parts[1].toDoubleOrNull() ?: return null
        return lat to lon
    }

val RecentRide.sid: String?
    get() = latLon?.let { spotId(it.first, it.second) }
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd mobile && ./gradlew :composeApp:testDebugUnitTest --tests "*RecentRideTest"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/model/RecentRide.kt \
        mobile/composeApp/src/commonTest/kotlin/org/hitchwiki/maps/model/RecentRideTest.kt
git commit -m "feat(mobile): RecentRide model + url->lat/lon/sid parsing"
```

---

### Task 5: `RecentRidesSource` + `HitchwikiApi.recentRides()`

The lazy data source for the recent set.

**Files:**
- Modify: `mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/data/HitchwikiApi.kt`
- Create: `mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/data/RecentRidesSource.kt`
- Test: `mobile/composeApp/src/commonTest/kotlin/org/hitchwiki/maps/data/RecentRidesSourceTest.kt`

**Interfaces:**
- Consumes: `HitchwikiApi`, `RecentRide`.
- Produces: `HitchwikiApi.recentRides(): List<RecentRide>`; `interface RecentRidesSource { suspend fun recent(): List<RecentRide> }`; `class ApiRecentRidesSource(api: HitchwikiApi) : RecentRidesSource`.

- [ ] **Step 1: Write the failing test**

```kotlin
package org.hitchwiki.maps.data
import io.ktor.client.engine.mock.*
import io.ktor.http.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.test.*
import kotlin.test.*

class RecentRidesSourceTest {
    @Test fun fetchesAndParsesSpotsRecent() = runTest {
        val body = """[{"url":"#1.0,2.0","hitchhiker_name":"alice","rating":5,"text":"good"},
                       {"url":"#3.0,4.0","hitchhiker_name":"bob","rating":3,"text":"ok"}]"""
        val api = HitchwikiApi(defaultHttpClient(MockEngine(MockEngineConfig().apply {
            addHandler { req ->
                assertTrue(req.url.encodedPath.endsWith("/spots_recent.json"))
                respond(body, HttpStatusCode.OK, headersOf(HttpHeaders.ContentType, "application/json"))
            }
            dispatcher = Dispatchers.Unconfined
        })), "https://example.test")
        val out = ApiRecentRidesSource(api).recent()
        assertEquals(2, out.size)
        assertEquals("alice", out[0].hitchhikerName)
    }
}
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd mobile && ./gradlew :composeApp:testDebugUnitTest --tests "*RecentRidesSourceTest"`
Expected: FAIL to compile — `recentRides` / `ApiRecentRidesSource` unresolved.

- [ ] **Step 3: Implement**

In `HitchwikiApi.kt`, add the import and method:
```kotlin
import org.hitchwiki.maps.model.RecentRide
```
```kotlin
    suspend fun recentRides(): List<RecentRide> = client.get("$baseUrl/spots_recent.json").body()
```
Create `RecentRidesSource.kt`:
```kotlin
package org.hitchwiki.maps.data
import org.hitchwiki.maps.model.RecentRide

/** Lazy source for the latest-rides list (spots_recent.json). Fetched only when Search opens. */
interface RecentRidesSource { suspend fun recent(): List<RecentRide> }

class ApiRecentRidesSource(private val api: HitchwikiApi) : RecentRidesSource {
    override suspend fun recent(): List<RecentRide> = api.recentRides()
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd mobile && ./gradlew :composeApp:testDebugUnitTest --tests "*RecentRidesSourceTest"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/data/HitchwikiApi.kt \
        mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/data/RecentRidesSource.kt \
        mobile/composeApp/src/commonTest/kotlin/org/hitchwiki/maps/data/RecentRidesSourceTest.kt
git commit -m "feat(mobile): RecentRidesSource + HitchwikiApi.recentRides()"
```

---

### Task 6: `SearchViewModel`

Load recent once (off-main), hold the query, expose filtered results. Entries without valid coordinates are dropped at load so every result is navigable.

**Files:**
- Create: `mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/ui/search/SearchUiState.kt`
- Create: `mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/ui/search/SearchViewModel.kt`
- Test: `mobile/composeApp/src/commonTest/kotlin/org/hitchwiki/maps/ui/search/SearchViewModelTest.kt`

**Interfaces:**
- Consumes: `RecentRidesSource`, `RecentRide`, `latLon`.
- Produces: `data class SearchUiState(loading, query, results, error)`; `class SearchViewModel(source, scope, workDispatcher = Dispatchers.Default)` with `fun load()`, `fun setQuery(q: String)`.

- [ ] **Step 1: Write the failing tests**

```kotlin
package org.hitchwiki.maps.ui.search
import org.hitchwiki.maps.data.RecentRidesSource
import org.hitchwiki.maps.model.RecentRide
import kotlinx.coroutines.test.*
import kotlin.test.*

class SearchViewModelTest {
    private class Fake(val list: List<RecentRide>) : RecentRidesSource {
        override suspend fun recent() = list
    }
    private val data = listOf(
        RecentRide(url = "#1.0,2.0", hitchhikerName = "Alice", text = "great ride"),
        RecentRide(url = "#3.0,4.0", hitchhikerName = "Bob", text = "long WAIT"),
        RecentRide(url = "#nope", hitchhikerName = "Carol", text = "unnavigable"),
    )

    @Test fun loadPopulatesRecentDroppingInvalidCoords() = runTest {
        val vm = SearchViewModel(Fake(data), this, StandardTestDispatcher(testScheduler))
        vm.load(); advanceUntilIdle()
        assertFalse(vm.state.value.loading)
        assertEquals(2, vm.state.value.results.size)   // "#nope" dropped
        assertNull(vm.state.value.error)
    }
    @Test fun queryFiltersByNameAndComment_caseInsensitive() = runTest {
        val vm = SearchViewModel(Fake(data), this, StandardTestDispatcher(testScheduler))
        vm.load(); advanceUntilIdle()
        vm.setQuery("alice")
        assertEquals(listOf("Alice"), vm.state.value.results.map { it.hitchhikerName })
        vm.setQuery("wait")   // matches Bob's comment, case-insensitive
        assertEquals(listOf("Bob"), vm.state.value.results.map { it.hitchhikerName })
        vm.setQuery("")       // empty -> all (navigable)
        assertEquals(2, vm.state.value.results.size)
    }
    @Test fun failureSetsErrorNotStuckLoading() = runTest {
        val failing = object : RecentRidesSource {
            override suspend fun recent(): List<RecentRide> = throw RuntimeException("boom")
        }
        val vm = SearchViewModel(failing, this, StandardTestDispatcher(testScheduler))
        vm.load(); advanceUntilIdle()
        assertFalse(vm.state.value.loading)
        assertNotNull(vm.state.value.error)
    }
}
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd mobile && ./gradlew :composeApp:testDebugUnitTest --tests "*SearchViewModelTest"`
Expected: FAIL to compile — `SearchViewModel` / `SearchUiState` unresolved.

- [ ] **Step 3: Implement**

`SearchUiState.kt`:
```kotlin
package org.hitchwiki.maps.ui.search
import org.hitchwiki.maps.model.RecentRide

data class SearchUiState(
    val loading: Boolean = false,
    val query: String = "",
    val results: List<RecentRide> = emptyList(),
    val error: String? = null,
)
```

`SearchViewModel.kt`:
```kotlin
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd mobile && ./gradlew :composeApp:testDebugUnitTest --tests "*SearchViewModelTest"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/ui/search/SearchUiState.kt \
        mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/ui/search/SearchViewModel.kt \
        mobile/composeApp/src/commonTest/kotlin/org/hitchwiki/maps/ui/search/SearchViewModelTest.kt
git commit -m "feat(mobile): SearchViewModel (lazy recent load + name/comment filter)"
```

---

### Task 7: Filters UI — `FilterSheet` + map filter entry

Add the filter bottom sheet and a ⚙ entry point on the map, wired to `MapViewModel.setFilter`. Android build + on-device check; no iOS compile here.

**Files:**
- Create: `mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/ui/map/FilterSheet.kt`
- Modify: `mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/ui/map/MapScreen.kt`

**Interfaces:**
- Consumes: `FilterState`, `MapViewModel.setFilter`, `MapUiState.filterState`.
- Produces: `@Composable fun FilterSheet(current: FilterState, onApply: (FilterState) -> Unit, onDismiss: () -> Unit)`.

- [ ] **Step 1: Create `FilterSheet.kt`**

```kotlin
package org.hitchwiki.maps.ui.map
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.selection.selectable
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun FilterSheet(current: FilterState, onApply: (FilterState) -> Unit, onDismiss: () -> Unit) {
    // Local edit copy; committed to the map on each change via onApply so the markers update live.
    var draft by remember(current) { mutableStateOf(current) }
    fun update(next: FilterState) { draft = next; onApply(next) }

    ModalBottomSheet(onDismissRequest = onDismiss) {
        Column(Modifier.fillMaxWidth().padding(16.dp)) {
            Text("Filters", style = MaterialTheme.typography.titleMedium)

            Text("Minimum rating", Modifier.padding(top = 12.dp), style = MaterialTheme.typography.labelLarge)
            Row(Modifier.padding(top = 4.dp)) {
                listOf(0 to "Any", 3 to "3+", 4 to "4+", 5 to "5").forEach { (value, label) ->
                    FilterChip(
                        selected = draft.minRating == value,
                        onClick = { update(draft.copy(minRating = value)) },
                        label = { Text(label) },
                        modifier = Modifier.padding(end = 8.dp),
                    )
                }
            }

            FilterToggle("Official spot (OSM)", draft.osm) { update(draft.copy(osm = it)) }
            FilterToggle("On Hitchwiki", draft.wiki) { update(draft.copy(wiki = it)) }
            FilterToggle("Car-pooling nearby", draft.cp) { update(draft.copy(cp = it)) }
            FilterToggle("At a gas station", draft.fuel) { update(draft.copy(fuel = it)) }

            TextButton(onClick = { update(FilterState()) }, modifier = Modifier.padding(top = 8.dp)) {
                Text("Reset")
            }
            Spacer(Modifier.height(24.dp))
        }
    }
}

@Composable
private fun FilterToggle(label: String, checked: Boolean, onCheckedChange: (Boolean) -> Unit) {
    Row(
        Modifier.fillMaxWidth().padding(top = 8.dp).selectable(checked) { onCheckedChange(!checked) },
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(label, Modifier.weight(1f))
        Switch(checked = checked, onCheckedChange = onCheckedChange)
    }
}
```

- [ ] **Step 2: Add the ⚙ entry + sheet to `MapScreen`**

In `MapScreen.kt`, inside the root `Box` (after the location FAB, before the summary-sheet block), add filter state and the button:
```kotlin
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
```
(`Alignment` and the layout/material imports are already wildcard-imported in `MapScreen.kt`.)

- [ ] **Step 3: Build**

Run: `cd mobile && ./gradlew :composeApp:assembleDebug`
Expected: BUILD SUCCESSFUL. (Do NOT run the iOS compile — that runs once in Task 8.)

- [ ] **Step 4: On-device check (human)**

Install and open the app; wait for spots. Tap **⚙ Filters** → the sheet opens. Set **4+** and toggle **Official spot (OSM)** → the markers (including cluster counts) narrow to matching spots; the button shows the active dot. **Reset** restores all. Record confirmation.

- [ ] **Step 5: Commit**

```bash
git add mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/ui/map/FilterSheet.kt \
        mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/ui/map/MapScreen.kt
git commit -m "feat(mobile): filter bottom sheet + map filter entry"
```

---

### Task 8: Search UI — screen, row, top search bar, nav + graph wiring

Add the search screen and its result row, the pinned top search bar on the map, the `search` nav route, and the `RecentRidesSource` graph wiring. This task ends the phase, so it also runs the single iOS compile guard.

**Files:**
- Create: `mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/ui/common/RecentRideRow.kt`
- Create: `mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/ui/search/SearchScreen.kt`
- Modify: `mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/ui/map/MapScreen.kt`
- Modify: `mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/ui/AppNav.kt`
- Modify: `mobile/composeApp/src/androidMain/kotlin/org/hitchwiki/maps/MainActivity.kt`

**Interfaces:**
- Consumes: `SearchViewModel`, `RecentRide`, `sid`, `latLon`, `RatingStars`, `MapViewModel.focusSpot`, `ApiRecentRidesSource`.
- Produces: `@Composable fun SearchScreen(viewModel, onResult: (Double, Double, String) -> Unit, onBack: () -> Unit)`; `@Composable fun RecentRideRow(ride, onClick)`; `MapScreen` gains `onOpenSearch: () -> Unit`; `AppNav` gains `recentSource: RecentRidesSource`.

- [ ] **Step 1: Create `RecentRideRow.kt`**

```kotlin
package org.hitchwiki.maps.ui.common
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import org.hitchwiki.maps.model.RecentRide

@Composable
fun RecentRideRow(ride: RecentRide, onClick: () -> Unit) {
    Column(Modifier.fillMaxWidth().clickable(onClick = onClick).padding(vertical = 8.dp, horizontal = 16.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(ride.hitchhikerName ?: "Anonymous", style = MaterialTheme.typography.titleSmall, modifier = Modifier.weight(1f))
            RatingStars(ride.rating)
        }
        ride.text?.takeIf { it.isNotBlank() }?.let {
            Text(it, style = MaterialTheme.typography.bodyMedium, maxLines = 2, overflow = TextOverflow.Ellipsis)
        }
        ride.submissionTime?.let {
            Text(it, style = MaterialTheme.typography.labelSmall)
        }
    }
    HorizontalDivider()
}
```

- [ ] **Step 2: Create `SearchScreen.kt`**

```kotlin
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
                        val sid = ride.let { org.hitchwiki.maps.model.sid(it) }
                        RecentRideRow(ride) { if (ll != null && sid != null) onResult(ll.first, ll.second, sid) }
                    }
                }
            }
        }
    }
}

// Local helper so the composable can read the extension `sid` without an import ambiguity.
private fun org.hitchwiki.maps.model.sid(r: org.hitchwiki.maps.model.RecentRide): String? =
    org.hitchwiki.maps.model.run { r.sid }
```

Note: if the `sid` extension resolves directly with `import org.hitchwiki.maps.model.sid`, prefer that and delete the local helper. Keep whichever compiles; the helper exists only to avoid an extension-resolution snag.

- [ ] **Step 3: Add the top search bar + `onOpenSearch` to `MapScreen`**

Add the parameter to `MapScreen`'s signature:
```kotlin
    onOpenSearch: () -> Unit,
```
Add a pinned search bar at the top (inside the root `Box`, e.g. just before the ⚙ button from Task 7); move the ⚙ button to sit beside it:
```kotlin
        Surface(
            onClick = onOpenSearch,
            tonalElevation = 3.dp,
            shape = MaterialTheme.shapes.large,
            modifier = Modifier.align(Alignment.TopCenter).fillMaxWidth().padding(16.dp),
        ) {
            Row(Modifier.padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
                Text("🔍  Search rides…", Modifier.weight(1f), style = MaterialTheme.typography.bodyLarge)
                Text(if (state.filterState.isActive) "⚙ •" else "⚙")
            }
        }
```
Change the Task-7 ⚙ button's `onClick` to open the sheet from a tap on the "⚙" affordance — simplest: keep the separate `showFilter` state, and make the whole search bar open search while a small trailing `IconButton`/`TextButton` opens the filter. Replace the trailing `Text("⚙…")` above with:
```kotlin
                TextButton(onClick = { showFilter = true }) { Text(if (state.filterState.isActive) "⚙ •" else "⚙") }
```
and remove the standalone `FilledTonalButton` added in Task 7 (the filter entry now lives in the bar). Keep the `showFilter` state and the `FilterSheet` block from Task 7.

- [ ] **Step 4: Wire the `search` route + `recentSource` in `AppNav`**

In `AppNav.kt`, add the import and parameter:
```kotlin
import org.hitchwiki.maps.data.RecentRidesSource
import org.hitchwiki.maps.ui.search.SearchScreen
import org.hitchwiki.maps.ui.search.SearchViewModel
```
Add `recentSource: RecentRidesSource,` to `AppNav`'s parameters. Pass `onOpenSearch` to the map destination:
```kotlin
        composable("map") {
            MapScreen(
                viewModel = mapViewModel,
                onRequestLocation = onRequestLocation,
                onOpenDetail = { sid, rating, count -> nav.navigate("spot/$sid?rating=$rating&count=$count") },
                onOpenSearch = { nav.navigate("search") },
            )
        }
```
Add the search destination:
```kotlin
        composable("search") {
            val vm = remember { SearchViewModel(recentSource, scope) }
            SearchScreen(
                viewModel = vm,
                onResult = { lat, lon, sid -> mapViewModel.focusSpot(lat, lon, sid); nav.popBackStack() },
                onBack = { nav.popBackStack() },
            )
        }
```

- [ ] **Step 5: Build the graph in `MainActivity`**

In `MainActivity.kt`, construct the source and pass it to `AppNav`:
```kotlin
        val recentSource = ApiRecentRidesSource(api)
```
(add `import org.hitchwiki.maps.data.ApiRecentRidesSource` — `api` already exists.) Then add `recentSource = recentSource,` to the `AppNav(...)` call.

- [ ] **Step 6: Build + iOS compile guard (end of phase)**

Run: `cd mobile && ./gradlew :composeApp:assembleDebug :composeApp:compileKotlinIosSimulatorArm64`
Expected: BUILD SUCCESSFUL. (This is the single iOS guard for the whole P3c increment.)

- [ ] **Step 7: On-device check (human)**

Install and open the app. Tap the **🔍 search bar** → the search screen opens showing **Recent rides**. Type a name/word → the list filters. Tap a result → the app returns to the map, flies to that spot, and its **summary sheet** opens. Back from the search screen returns to the map. Record confirmation.

- [ ] **Step 8: Commit**

```bash
git add mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/ui/common/RecentRideRow.kt \
        mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/ui/search/SearchScreen.kt \
        mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/ui/map/MapScreen.kt \
        mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/ui/AppNav.kt \
        mobile/composeApp/src/androidMain/kotlin/org/hitchwiki/maps/MainActivity.kt
git commit -m "feat(mobile): search/recent screen + top search bar + nav wiring"
```

---

## Self-Review

**Spec coverage:**
- Top search bar + ⚙ filter icon on the map → Task 7 (⚙ + sheet) + Task 8 (search bar). ✓
- Search screen, empty→Recent, name/comment filter → Tasks 6 + 8. ✓
- Search data = spots_recent, lazy → Tasks 5 (source) + 8 (loaded on screen mount). ✓
- Result tap → focusSpot (camera + summary sheet) → Task 3 (focusSpot) + Task 8 (wiring). ✓
- Filters: min rating + osm/wiki/cp/fuel, rebuild under clustering → Tasks 2 + 3 + 7. ✓
- Fast `buildSpotsGeoJson` → Task 1. ✓
- `RecentRide` url→lat/lon/sid, skip malformed → Task 4 (+ dropped at load in Task 6). ✓
- Testing matrix (RecentRide parse, search filter, applyFilters, geojson equivalence + subset, MapViewModel setFilter/focusSpot, SearchViewModel) → Tasks 1,2,3,4,5,6. ✓
- iOS guard once at end → Task 8 Step 6. ✓

**Placeholder scan:** No TBD/TODO; every code step shows full code. The one soft spot is the `sid` extension resolution in Task 8 Step 2 — handled explicitly with a fallback helper and an instruction to prefer the direct import if it compiles.

**Type consistency:** `FilterState` (package `ui.map`) used by `applyFilters` (package `data`, imports it) and `MapUiState`/`MapViewModel` (same package). `RecentRide` + `latLon`/`sid` (package `model`) used by `SearchViewModel` and `SearchScreen`. `focusSpot(lat, lon, sid)` signature matches `SearchScreen.onResult` and the `AppNav` wiring. `recentRides()`/`RecentRidesSource.recent()` names consistent across Tasks 5/6/8. `workDispatcher` injection matches the existing `MapViewModel` pattern.

## Deferred (not in this plan)

Full-history/server search; offline PMTiles packs; auth/write (P4/P5); iOS map; the broader load-perf slice beyond the `buildSpotsGeoJson` speedup.
