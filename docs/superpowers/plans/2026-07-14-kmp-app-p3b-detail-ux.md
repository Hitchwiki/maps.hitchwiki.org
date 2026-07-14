# KMP App P3b — Two-Tier Spot Detail UX (Android) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tap a marker → an enriched summary sheet (rating, avg wait, last 3 rides, "Full detail" button) → a dedicated informational full-detail screen (header stats, all ride cards, OSM/Hitchwiki link chips), navigated via JetBrains Compose Multiplatform navigation. Android functional; shared UI + nav compile for iOS.

**Architecture:** A testable shared core in `commonMain` — pure `spotLinks()`/`formatRideDate()`/`ridesNewestFirst()` helpers, a `MapViewModel` addition (selected rating/count via a `sid→Spot` map), and a `SpotDetailViewModel` (fetches `SpotDetail` by `sid`) — drives common Compose UI (`RatingStars`, `RideCard`, `SpotSummarySheet`, `SpotDetailScreen`) wired through a `NavHost` in `AppNav`. Only `PlatformMap` stays a platform stub; everything P3b adds is common.

**Tech Stack:** Kotlin 2.1.0, Compose Multiplatform 1.7.3, `org.jetbrains.androidx.navigation:navigation-compose:2.8.0-alpha10`, `org.jetbrains.kotlinx:kotlinx-datetime:0.6.1`, Ktor 3.0.1, kotlinx-coroutines 1.9.0, JUnit4 + kotlin-test.

## Global Constraints

- **Reuse existing code, don't fork it.** `Spot`, `SpotDetail`/`SpotInfo`/`OsmRef`/`SpotRide`, `HitchwikiApi`, `SpotRepository`, `SpotDetailSource`/`ApiSpotDetailSource`, `MapViewModel`, `MapUiState`, `MapScreen`, `spotId`, `appJson`, `LatLng`, `PlatformMap`, `LocationProvider` already exist — consume them.
- **`OsmRef` already landed** (commit 287b2cf): `SpotInfo.carPooling`/`fuel` are `OsmRef(id: Long, osmType: String)?`. Build car-pooling/gas URLs from `osmType`/`id`.
- **Link URLs are exact (match the web):**
  - OSM node: `https://www.openstreetmap.org/node/{osmId}`
  - car-pooling / gas: `https://www.openstreetmap.org/{osmType}/{id}`
  - Hitchwiki article/map: the stored URL verbatim.
- **Nav routes:** `map` and `spot/{sid}?rating={rating}&count={count}`. `sid` is a single path segment (no slash). `rating` is Float, `count` is Int; a missing/malformed arg must not crash (default it).
- **rating/count come from the marker,** not the per-spot JSON (which has no aggregate rating) — thread them through nav args.
- **MapLibre stays out of commonMain and P3b doesn't touch `PlatformMap`.** iOS `PlatformMap` stub is unchanged; every P3b addition compiles for iOS (guarded).
- **MVP is Android-only;** iOS is design-only but `compileKotlinIosSimulatorArm64` must stay green.
- **TDD, DRY, YAGNI, frequent commits.** Tasks 1–4 are red→green→commit. Tasks 5–8 are Compose/nav integration: the "test" is a successful build + a named manual check; commit each.
- Package root `org.hitchwiki.maps`.

---

## File Structure

```
mobile/composeApp/src/
├── commonMain/kotlin/org/hitchwiki/maps/
│   ├── data/SpotLinks.kt              spotLinks(SpotInfo): List<SpotLink>     [Task 1]
│   ├── data/RideSort.kt               ridesNewestFirst(List<SpotRide>)        [Task 4]
│   ├── util/RideDate.kt               formatRideDate(iso): String             [Task 2]
│   ├── ui/map/MapUiState.kt           + selectedRating/selectedReviewCount    [Task 3]
│   ├── ui/map/MapViewModel.kt         + sid→Spot map, set selected r/count    [Task 3]
│   ├── ui/detail/SpotDetailUiState.kt                                          [Task 4]
│   ├── ui/detail/SpotDetailViewModel.kt  fetch SpotDetail by sid              [Task 4]
│   ├── ui/common/RatingStars.kt       ★ row for an Int rating                 [Task 5]
│   ├── ui/common/RideCard.kt          one ride's card                         [Task 5]
│   ├── ui/map/SpotSummarySheet.kt     enriched summary sheet                  [Task 6]
│   ├── ui/map/MapScreen.kt            use SpotSummarySheet + onOpenDetail      [Task 6]
│   ├── ui/detail/SpotDetailScreen.kt  full screen                             [Task 7]
│   └── ui/AppNav.kt                   NavHost(map, spot/{sid})                 [Task 8]
├── commonTest/kotlin/org/hitchwiki/maps/
│   ├── data/SpotLinksTest.kt                                                   [Task 1]
│   ├── util/RideDateTest.kt                                                    [Task 2]
│   ├── ui/map/MapViewModelSelectedTest.kt                                      [Task 3]
│   ├── data/RideSortTest.kt                                                    [Task 4]
│   └── ui/detail/SpotDetailViewModelTest.kt                                    [Task 4]
└── androidMain/kotlin/org/hitchwiki/maps/MainActivity.kt  host AppNav          [Task 8]
```

---

## Task 1: `spotLinks` — pure OSM/Hitchwiki link builder

**Files:**
- Create: `mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/data/SpotLinks.kt`
- Test: `mobile/composeApp/src/commonTest/kotlin/org/hitchwiki/maps/data/SpotLinksTest.kt`

**Interfaces:**
- Consumes: `SpotInfo`/`OsmRef` (existing).
- Produces: `data class SpotLink(val emoji: String, val label: String, val url: String)`; `fun spotLinks(spot: SpotInfo): List<SpotLink>` — present links only, in the order OSM node, car-pooling, gas, Hitchwiki article, Hitchwiki map.

- [ ] **Step 1: Write the failing test**

```kotlin
package org.hitchwiki.maps.data
import org.hitchwiki.maps.model.OsmRef
import org.hitchwiki.maps.model.SpotInfo
import kotlin.test.*

class SpotLinksTest {
    @Test fun allLinksInOrder() {
        val links = spotLinks(SpotInfo(
            osmId = 111L,
            carPooling = OsmRef(222L, "way"),
            fuel = OsmRef(333L, "node"),
            hitchwikiArticle = "https://hitchwiki.org/en/A",
            hitchwikiMap = "https://hitchwiki.org/maps/B",
        ))
        assertEquals(5, links.size)
        assertEquals("https://www.openstreetmap.org/node/111", links[0].url)
        assertEquals("https://www.openstreetmap.org/way/222", links[1].url)
        assertEquals("https://www.openstreetmap.org/node/333", links[2].url)
        assertEquals("https://hitchwiki.org/en/A", links[3].url)
        assertEquals("https://hitchwiki.org/maps/B", links[4].url)
        assertEquals("Official hitchhiking spot", links[0].label)
    }
    @Test fun emptySpotHasNoLinks() {
        assertTrue(spotLinks(SpotInfo()).isEmpty())
    }
    @Test fun onlyPresentLinksIncluded() {
        val links = spotLinks(SpotInfo(osmId = 9L, hitchwikiArticle = "https://x"))
        assertEquals(2, links.size)
        assertEquals("https://www.openstreetmap.org/node/9", links[0].url)
        assertEquals("https://x", links[1].url)
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mobile && ./gradlew :composeApp:testDebugUnitTest --tests "org.hitchwiki.maps.data.SpotLinksTest"`
Expected: FAIL — `spotLinks`/`SpotLink` unresolved.

- [ ] **Step 3: Implement**

```kotlin
package org.hitchwiki.maps.data
import org.hitchwiki.maps.model.SpotInfo

data class SpotLink(val emoji: String, val label: String, val url: String)

// Present links only, in a fixed display order. URLs match the web spot pane exactly.
fun spotLinks(spot: SpotInfo): List<SpotLink> = buildList {
    spot.osmId?.let { add(SpotLink("🚏", "Official hitchhiking spot", "https://www.openstreetmap.org/node/$it")) }
    spot.carPooling?.let { add(SpotLink("🚗", "Car pooling spot", "https://www.openstreetmap.org/${it.osmType}/${it.id}")) }
    spot.fuel?.let { add(SpotLink("⛽", "Gas station", "https://www.openstreetmap.org/${it.osmType}/${it.id}")) }
    spot.hitchwikiArticle?.let { add(SpotLink("📄", "Mentioned on Hitchwiki", it)) }
    spot.hitchwikiMap?.let { add(SpotLink("🗺️", "On Hitchwiki", it)) }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd mobile && ./gradlew :composeApp:testDebugUnitTest --tests "org.hitchwiki.maps.data.SpotLinksTest"`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/data/SpotLinks.kt \
        mobile/composeApp/src/commonTest/kotlin/org/hitchwiki/maps/data/SpotLinksTest.kt
git commit -m "feat(mobile): spotLinks pure OSM/Hitchwiki link builder"
```

---

## Task 2: `formatRideDate` — ISO → "Month YYYY" (kotlinx-datetime)

**Files:**
- Modify: `mobile/gradle/libs.versions.toml` + `mobile/composeApp/build.gradle.kts` — add kotlinx-datetime to commonMain.
- Create: `mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/util/RideDate.kt`
- Test: `mobile/composeApp/src/commonTest/kotlin/org/hitchwiki/maps/util/RideDateTest.kt`

**Interfaces:**
- Produces: `fun formatRideDate(iso: String?): String` — `"January 2024"` for a parseable ISO datetime; `""` for null/blank; a `YYYY-MM-DD` fallback for an unparseable-but-date-prefixed string.

- [ ] **Step 1: Add the dependency**

`libs.versions.toml`: `[versions]` add `kotlinx-datetime = "0.6.1"`; `[libraries]` add
`kotlinx-datetime = { module = "org.jetbrains.kotlinx:kotlinx-datetime", version.ref = "kotlinx-datetime" }`.
`composeApp/build.gradle.kts` `commonMain.dependencies`: `implementation(libs.kotlinx.datetime)`.

- [ ] **Step 2: Write the failing test**

```kotlin
package org.hitchwiki.maps.util
import kotlin.test.*

class RideDateTest {
    @Test fun formatsFullIsoAsMonthYear() {
        assertEquals("January 2024", formatRideDate("2024-01-15T14:30:00"))
        assertEquals("December 2023", formatRideDate("2023-12-01T00:00:00"))
    }
    @Test fun nullOrBlankIsEmpty() {
        assertEquals("", formatRideDate(null))
        assertEquals("", formatRideDate(""))
    }
    @Test fun unparseableFallsBackToDatePrefix() {
        // A date-only string has no time component, so LocalDateTime.parse fails → prefix fallback.
        assertEquals("2024-01-15", formatRideDate("2024-01-15"))
    }
}
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd mobile && ./gradlew :composeApp:testDebugUnitTest --tests "org.hitchwiki.maps.util.RideDateTest"`
Expected: FAIL — `formatRideDate` unresolved.

- [ ] **Step 4: Implement**

```kotlin
package org.hitchwiki.maps.util
import kotlinx.datetime.LocalDateTime

private val MONTHS = listOf(
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)

/** Format a ride's ISO timestamp for display as "Month YYYY". Ride timestamps come from
 *  Python isoformat() (e.g. "2024-01-15T14:30:00"). Returns "" for null/blank, and falls back
 *  to the first 10 chars (YYYY-MM-DD) if the value has no parseable time component. */
fun formatRideDate(iso: String?): String {
    if (iso.isNullOrBlank()) return ""
    return try {
        val dt = LocalDateTime.parse(iso)
        "${MONTHS[dt.monthNumber - 1]} ${dt.year}"
    } catch (e: Exception) {
        iso.take(10)
    }
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd mobile && ./gradlew :composeApp:testDebugUnitTest --tests "org.hitchwiki.maps.util.RideDateTest"`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add mobile/gradle/libs.versions.toml mobile/composeApp/build.gradle.kts \
        mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/util/RideDate.kt \
        mobile/composeApp/src/commonTest/kotlin/org/hitchwiki/maps/util/RideDateTest.kt
git commit -m "feat(mobile): formatRideDate ISO->Month YYYY via kotlinx-datetime"
```

---

## Task 3: `MapViewModel` selected rating/review-count

**Files:**
- Modify: `mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/ui/map/MapUiState.kt`
- Modify: `mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/ui/map/MapViewModel.kt`
- Test: `mobile/composeApp/src/commonTest/kotlin/org/hitchwiki/maps/ui/map/MapViewModelSelectedTest.kt`

**Interfaces:**
- Adds `selectedRating: Double?` + `selectedReviewCount: Int?` to `MapUiState`.
- On `selectSpot(sid)`, look up the tapped `Spot` (by `sid`) and set them; `clearSelection()` resets them. `load()` builds a `sid→Spot` map so the lookup is O(1).

- [ ] **Step 1: Write the failing test**

```kotlin
package org.hitchwiki.maps.ui.map
import org.hitchwiki.maps.data.*
import org.hitchwiki.maps.model.Spot
import org.hitchwiki.maps.model.SpotDetail
import io.ktor.client.engine.mock.*
import io.ktor.http.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.test.*
import kotlin.test.*

class MapViewModelSelectedTest {
    private fun repoReturning(body: String) = SpotRepository(
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
        override suspend fun detail(sid: String): SpotDetail = SpotDetail()
    }

    @Test fun selectSpotSetsRatingAndCountFromLoadedSpot() = runTest {
        // spot at lat 1.0 lon 2.0 → sid "1.00000_2.00000", rating 4.0, review_count 7
        val vm = MapViewModel(
            repoReturning("""[{"lat":1.0,"lon":2.0,"rating":4.0,"review_count":7}]"""), noDetail, this)
        vm.load(); advanceUntilIdle()
        vm.selectSpot("1.00000_2.00000"); advanceUntilIdle()
        assertEquals(4.0, vm.state.value.selectedRating)
        assertEquals(7, vm.state.value.selectedReviewCount)
    }
    @Test fun clearSelectionResetsRatingAndCount() = runTest {
        val vm = MapViewModel(
            repoReturning("""[{"lat":1.0,"lon":2.0,"rating":4.0,"review_count":7}]"""), noDetail, this)
        vm.load(); advanceUntilIdle()
        vm.selectSpot("1.00000_2.00000"); advanceUntilIdle()
        vm.clearSelection()
        assertNull(vm.state.value.selectedRating); assertNull(vm.state.value.selectedReviewCount)
    }
    @Test fun unknownSidLeavesRatingNull() = runTest {
        val vm = MapViewModel(repoReturning("""[]"""), noDetail, this)
        vm.load(); advanceUntilIdle()
        vm.selectSpot("9.99999_9.99999"); advanceUntilIdle()
        assertNull(vm.state.value.selectedRating)
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mobile && ./gradlew :composeApp:testDebugUnitTest --tests "org.hitchwiki.maps.ui.map.MapViewModelSelectedTest"`
Expected: FAIL — `selectedRating`/`selectedReviewCount` unresolved.

- [ ] **Step 3: Implement**

In `MapUiState.kt`, add two fields (place after `detailError`):
```kotlin
    val selectedRating: Double? = null,
    val selectedReviewCount: Int? = null,
```

In `MapViewModel.kt`:
- Add a private field and populate it in `load()` after fetching:
```kotlin
    // sid → Spot, built once per load so selectSpot is O(1) over ~35k spots.
    private var spotsBySid: Map<String, org.hitchwiki.maps.model.Spot> = emptyMap()
```
In `load()`'s success path, before/with the state update:
```kotlin
    val geo = buildSpotsGeoJson(fresh)
    spotsBySid = fresh.associateBy { org.hitchwiki.maps.util.spotId(it.lat, it.lon) }
    _state.update { it.copy(loading = false, spots = fresh, geoJson = geo) }
```
- In `selectSpot(sid)`'s initial `_state.update`, also set rating/count from the lookup:
```kotlin
    fun selectSpot(sid: String) {
        val s = spotsBySid[sid]
        _state.update { it.copy(
            selectedSid = sid, selectedDetail = null, detailLoading = true, detailError = null,
            selectedRating = s?.rating, selectedReviewCount = s?.reviewCount,
        ) }
        // ... existing scope.launch { details.detail(sid) ... } unchanged
    }
```
- In `clearSelection()`, also reset them:
```kotlin
    fun clearSelection() = _state.update { it.copy(
        selectedSid = null, selectedDetail = null, detailLoading = false, detailError = null,
        selectedRating = null, selectedReviewCount = null,
    ) }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd mobile && ./gradlew :composeApp:testDebugUnitTest --tests "org.hitchwiki.maps.ui.map.MapViewModelSelectedTest"`
Expected: PASS (3 tests). Also re-run the existing `MapViewModelTest` to confirm no regression:
`cd mobile && ./gradlew :composeApp:testDebugUnitTest --tests "org.hitchwiki.maps.ui.map.MapViewModelTest"` → PASS.

- [ ] **Step 5: Commit**

```bash
git add mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/ui/map/MapUiState.kt \
        mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/ui/map/MapViewModel.kt \
        mobile/composeApp/src/commonTest/kotlin/org/hitchwiki/maps/ui/map/MapViewModelSelectedTest.kt
git commit -m "feat(mobile): MapViewModel exposes selected spot rating/review count"
```

---

## Task 4: `ridesNewestFirst` + `SpotDetailViewModel`

**Files:**
- Create: `mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/data/RideSort.kt`
- Create: `mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/ui/detail/SpotDetailUiState.kt`
- Create: `mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/ui/detail/SpotDetailViewModel.kt`
- Test: `mobile/composeApp/src/commonTest/kotlin/org/hitchwiki/maps/data/RideSortTest.kt`
- Test: `mobile/composeApp/src/commonTest/kotlin/org/hitchwiki/maps/ui/detail/SpotDetailViewModelTest.kt`

**Interfaces:**
- `fun ridesNewestFirst(rides: List<SpotRide>): List<SpotRide>` — sorted by `submissionTime` descending (ISO strings sort lexicographically); rides with a null `submissionTime` go last.
- `data class SpotDetailUiState(loading, detail, error)`; `class SpotDetailViewModel(sid: String, details: SpotDetailSource, scope: CoroutineScope)` with `val state: StateFlow<SpotDetailUiState>` and `fun load()`.

- [ ] **Step 1: Write the failing tests**

`RideSortTest.kt`:
```kotlin
package org.hitchwiki.maps.data
import org.hitchwiki.maps.model.SpotRide
import kotlin.test.*

class RideSortTest {
    private fun ride(id: String, t: String?) = SpotRide(id = id, submissionTime = t)
    @Test fun sortsNewestFirstNullsLast() {
        val sorted = ridesNewestFirst(listOf(
            ride("a", "2023-01-01T00:00:00"),
            ride("b", "2024-06-01T00:00:00"),
            ride("c", null),
            ride("d", "2024-01-01T00:00:00"),
        ))
        assertEquals(listOf("b", "d", "a", "c"), sorted.map { it.id })
    }
}
```

`SpotDetailViewModelTest.kt`:
```kotlin
package org.hitchwiki.maps.ui.detail
import org.hitchwiki.maps.data.SpotDetailSource
import org.hitchwiki.maps.model.SpotDetail
import org.hitchwiki.maps.model.SpotInfo
import kotlinx.coroutines.test.*
import kotlin.test.*

class SpotDetailViewModelTest {
    private fun source(result: () -> SpotDetail) = object : SpotDetailSource {
        override suspend fun detail(sid: String): SpotDetail = result()
    }
    @Test fun loadFetchesDetail() = runTest {
        val vm = SpotDetailViewModel("sid1", source { SpotDetail(spot = SpotInfo(wait = 9)) }, this)
        vm.load(); advanceUntilIdle()
        assertFalse(vm.state.value.loading)
        assertEquals(9, vm.state.value.detail?.spot?.wait)
        assertNull(vm.state.value.error)
    }
    @Test fun loadFailureSetsError() = runTest {
        val vm = SpotDetailViewModel("sid1", source { throw RuntimeException("boom") }, this)
        vm.load(); advanceUntilIdle()
        assertFalse(vm.state.value.loading)
        assertNull(vm.state.value.detail)
        assertNotNull(vm.state.value.error)
    }
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd mobile && ./gradlew :composeApp:testDebugUnitTest --tests "org.hitchwiki.maps.data.RideSortTest" --tests "org.hitchwiki.maps.ui.detail.SpotDetailViewModelTest"`
Expected: FAIL — `ridesNewestFirst`/`SpotDetailViewModel`/`SpotDetailUiState` unresolved.

- [ ] **Step 3: Implement**

`data/RideSort.kt`:
```kotlin
package org.hitchwiki.maps.data
import org.hitchwiki.maps.model.SpotRide

// Newest-first by submissionTime (ISO strings sort lexicographically); null times go last.
fun ridesNewestFirst(rides: List<SpotRide>): List<SpotRide> =
    rides.sortedWith(compareByDescending(nullsFirst()) { it.submissionTime })
```
Note: `compareByDescending(nullsFirst())` puts nulls LAST under descending order (nullsFirst makes null the smallest; descending then places it last). Verify against the test; if ordering is off, use `sortedWith(compareByDescending<SpotRide> { it.submissionTime == null }.thenByDescending { it.submissionTime })` — pick whichever the test confirms.

`ui/detail/SpotDetailUiState.kt`:
```kotlin
package org.hitchwiki.maps.ui.detail
import org.hitchwiki.maps.model.SpotDetail

data class SpotDetailUiState(
    val loading: Boolean = false,
    val detail: SpotDetail? = null,
    val error: String? = null,
)
```

`ui/detail/SpotDetailViewModel.kt`:
```kotlin
package org.hitchwiki.maps.ui.detail
import org.hitchwiki.maps.data.SpotDetailSource
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch

class SpotDetailViewModel(
    private val sid: String,
    private val details: SpotDetailSource,
    private val scope: CoroutineScope,
) {
    private val _state = MutableStateFlow(SpotDetailUiState())
    val state: StateFlow<SpotDetailUiState> = _state.asStateFlow()

    fun load() {
        _state.update { it.copy(loading = true, error = null) }
        scope.launch {
            try {
                val d = details.detail(sid)
                _state.update { it.copy(loading = false, detail = d) }
            } catch (e: Throwable) {
                _state.update { it.copy(loading = false, error = e.message ?: "Failed to load spot") }
            }
        }
    }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd mobile && ./gradlew :composeApp:testDebugUnitTest --tests "org.hitchwiki.maps.data.RideSortTest" --tests "org.hitchwiki.maps.ui.detail.SpotDetailViewModelTest"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/data/RideSort.kt \
        mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/ui/detail/SpotDetailUiState.kt \
        mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/ui/detail/SpotDetailViewModel.kt \
        mobile/composeApp/src/commonTest/kotlin/org/hitchwiki/maps/data/RideSortTest.kt \
        mobile/composeApp/src/commonTest/kotlin/org/hitchwiki/maps/ui/detail/SpotDetailViewModelTest.kt
git commit -m "feat(mobile): ridesNewestFirst + SpotDetailViewModel"
```

---

## Task 5: Shared UI — `RatingStars` + `RideCard`

**Files:**
- Create: `mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/ui/common/RatingStars.kt`
- Create: `mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/ui/common/RideCard.kt`

**Interfaces:**
- Consumes: `SpotRide`, `formatRideDate`.
- Produces: `@Composable fun RatingStars(rating: Int?, modifier: Modifier = Modifier)`; `@Composable fun RideCard(ride: SpotRide, modifier: Modifier = Modifier)`.

- [ ] **Step 1: Implement (build-verified — Compose UI, no unit test)**

`ui/common/RatingStars.kt`:
```kotlin
package org.hitchwiki.maps.ui.common
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier

@Composable
fun RatingStars(rating: Int?, modifier: Modifier = Modifier) {
    // Filled/empty stars for a 1..5 rating; nothing when unrated.
    val r = rating?.coerceIn(0, 5) ?: return
    Text("★".repeat(r) + "☆".repeat(5 - r), modifier = modifier)
}
```

`ui/common/RideCard.kt`:
```kotlin
package org.hitchwiki.maps.ui.common
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import org.hitchwiki.maps.model.SpotRide
import org.hitchwiki.maps.util.formatRideDate

@Composable
fun RideCard(ride: SpotRide, modifier: Modifier = Modifier) {
    Card(modifier.fillMaxWidth().padding(vertical = 4.dp)) {
        Column(Modifier.padding(12.dp)) {
            Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                RatingStars(ride.rating)
                Spacer(Modifier.weight(1f))
                Text(ride.hitchhikerName, style = MaterialTheme.typography.labelMedium)
            }
            val date = formatRideDate(ride.submissionTime)
            val meta = buildList {
                if (date.isNotEmpty()) add(date)
                ride.wait?.let { add("waited $it min") }
                ride.distance?.let { add("$it km") }
            }.joinToString(" · ")
            if (meta.isNotEmpty()) Text(meta, style = MaterialTheme.typography.bodySmall)
            ride.comment?.let { Text(it, style = MaterialTheme.typography.bodyMedium, modifier = Modifier.padding(top = 4.dp)) }
        }
    }
}
```

- [ ] **Step 2: Build both targets**

Run: `cd mobile && ./gradlew :composeApp:assembleDebug :composeApp:compileKotlinIosSimulatorArm64`
Expected: BUILD SUCCESSFUL.

- [ ] **Step 3: Commit**

```bash
git add mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/ui/common
git commit -m "feat(mobile): shared RatingStars + RideCard composables"
```

---

## Task 6: `SpotSummarySheet` + wire it into `MapScreen`

**Files:**
- Create: `mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/ui/map/SpotSummarySheet.kt`
- Modify: `mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/ui/map/MapScreen.kt`

**Interfaces:**
- Consumes: `MapUiState`, `RatingStars`, `RideCard`, `ridesNewestFirst`.
- Produces: `@Composable fun SpotSummarySheet(state: MapUiState, onDismiss: () -> Unit, onOpenDetail: () -> Unit)`. `MapScreen` gains a new param `onOpenDetail: (sid: String, rating: Float, count: Int) -> Unit`.

- [ ] **Step 1: Implement `SpotSummarySheet`**

```kotlin
package org.hitchwiki.maps.ui.map
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import org.hitchwiki.maps.data.ridesNewestFirst
import org.hitchwiki.maps.ui.common.RatingStars
import org.hitchwiki.maps.ui.common.RideCard

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SpotSummarySheet(state: MapUiState, onDismiss: () -> Unit, onOpenDetail: () -> Unit) {
    ModalBottomSheet(onDismissRequest = onDismiss) {
        Column(Modifier.fillMaxWidth().padding(16.dp)) {
            Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                RatingStars(state.selectedRating?.let { kotlin.math.round(it).toInt() })
                Spacer(Modifier.width(8.dp))
                state.selectedReviewCount?.let { Text("$it reviews", style = MaterialTheme.typography.labelMedium) }
            }
            when {
                state.detailLoading -> Text("Loading…", Modifier.padding(top = 8.dp))
                state.detailError != null -> Text("Couldn't load spot details.", Modifier.padding(top = 8.dp))
                state.selectedDetail != null -> {
                    val d = state.selectedDetail!!
                    d.spot.wait?.let { Text("Avg wait: $it min", Modifier.padding(top = 8.dp)) }
                    ridesNewestFirst(d.rides).take(3).forEach { RideCard(it) }
                    if (d.rides.size > 3) {
                        TextButton(onClick = onOpenDetail, modifier = Modifier.padding(top = 4.dp)) {
                            Text("Full detail (${d.rides.size} rides)")
                        }
                    } else {
                        TextButton(onClick = onOpenDetail, modifier = Modifier.padding(top = 4.dp)) { Text("Full detail") }
                    }
                }
                else -> Text("No details available.", Modifier.padding(top = 8.dp))
            }
            Spacer(Modifier.height(24.dp))
        }
    }
}
```

- [ ] **Step 2: Wire into `MapScreen`**

Change `MapScreen`'s signature to add `onOpenDetail: (String, Float, Int) -> Unit`, and replace the inline `ModalBottomSheet` block with:
```kotlin
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
```
Keep the rest of `MapScreen` (map, attribution, loading/error, FAB) unchanged.

- [ ] **Step 3: Build both targets**

Run: `cd mobile && ./gradlew :composeApp:assembleDebug :composeApp:compileKotlinIosSimulatorArm64`
Expected: BUILD SUCCESSFUL.

- [ ] **Step 4: Commit**

```bash
git add mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/ui/map/SpotSummarySheet.kt \
        mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/ui/map/MapScreen.kt
git commit -m "feat(mobile): enriched SpotSummarySheet with rating + last 3 rides + Full detail"
```

---

## Task 7: `SpotDetailScreen` — full informational screen

**Files:**
- Create: `mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/ui/detail/SpotDetailScreen.kt`

**Interfaces:**
- Consumes: `SpotDetailViewModel`, `spotLinks`, `ridesNewestFirst`, `RatingStars`, `RideCard`, `LocalUriHandler`.
- Produces: `@Composable fun SpotDetailScreen(viewModel: SpotDetailViewModel, rating: Float, reviewCount: Int, onBack: () -> Unit)`.

- [ ] **Step 1: Implement**

```kotlin
package org.hitchwiki.maps.ui.detail
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.unit.dp
import org.hitchwiki.maps.data.ridesNewestFirst
import org.hitchwiki.maps.data.spotLinks
import org.hitchwiki.maps.ui.common.RatingStars
import org.hitchwiki.maps.ui.common.RideCard

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SpotDetailScreen(viewModel: SpotDetailViewModel, rating: Float, reviewCount: Int, onBack: () -> Unit) {
    val state by viewModel.state.collectAsState()
    val uriHandler = LocalUriHandler.current
    LaunchedEffect(Unit) { viewModel.load() }

    Scaffold(topBar = {
        TopAppBar(
            title = { Text("Spot") },
            navigationIcon = { IconButton(onClick = onBack) { Text("‹") } },
        )
    }) { padding ->
        LazyColumn(Modifier.padding(padding).fillMaxSize().padding(horizontal = 16.dp)) {
            item {
                Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically, modifier = Modifier.padding(vertical = 8.dp)) {
                    RatingStars(kotlin.math.round(rating).toInt())
                    Spacer(Modifier.width(8.dp))
                    Text("$reviewCount reviews", style = MaterialTheme.typography.labelMedium)
                }
                val d = state.detail
                d?.spot?.wait?.let { Text("Avg wait: $it min") }
                d?.spot?.distance?.let { Text("Avg ride: $it km") }
                d?.spot?.let { info ->
                    spotLinks(info).forEach { link ->
                        TextButton(onClick = { uriHandler.openUri(link.url) }) { Text("${link.emoji} ${link.label}") }
                    }
                }
                when {
                    state.loading -> Text("Loading…", Modifier.padding(vertical = 8.dp))
                    state.error != null -> Text("Couldn't load this spot.", Modifier.padding(vertical = 8.dp))
                    d != null && d.rides.isEmpty() -> Text("No rides logged here yet.", Modifier.padding(vertical = 8.dp))
                }
            }
            state.detail?.let { d ->
                items(ridesNewestFirst(d.rides)) { ride -> RideCard(ride) }
            }
        }
    }
}
```

- [ ] **Step 2: Build both targets**

Run: `cd mobile && ./gradlew :composeApp:assembleDebug :composeApp:compileKotlinIosSimulatorArm64`
Expected: BUILD SUCCESSFUL. (If `androidx.compose.foundation.lazy.items` import differs, use the one the compiler resolves.)

- [ ] **Step 3: Commit**

```bash
git add mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/ui/detail/SpotDetailScreen.kt
git commit -m "feat(mobile): SpotDetailScreen with header, ride list, link chips"
```

---

## Task 8: `AppNav` + navigation-compose + `MainActivity` wiring

**Files:**
- Modify: `mobile/gradle/libs.versions.toml` + `mobile/composeApp/build.gradle.kts` — add navigation-compose to commonMain.
- Create: `mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/ui/AppNav.kt`
- Modify: `mobile/composeApp/src/androidMain/kotlin/org/hitchwiki/maps/MainActivity.kt`

**Interfaces:**
- Consumes: `MapScreen`, `SpotDetailScreen`, `SpotDetailViewModel`, `MapViewModel`, `SpotDetailSource`.
- Produces: `@Composable fun AppNav(mapViewModel: MapViewModel, detailSource: SpotDetailSource, scope: CoroutineScope, onRequestLocation: () -> Unit)` hosting the `NavHost`.

- [ ] **Step 1: Add the dependency**

`libs.versions.toml`: `[versions]` add `navigation-compose = "2.8.0-alpha10"`; `[libraries]` add
`navigation-compose = { module = "org.jetbrains.androidx.navigation:navigation-compose", version.ref = "navigation-compose" }`.
`composeApp/build.gradle.kts` `commonMain.dependencies`: `implementation(libs.navigation.compose)`.

- [ ] **Step 2: Implement `AppNav`**

```kotlin
package org.hitchwiki.maps.ui
import androidx.compose.runtime.Composable
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import kotlinx.coroutines.CoroutineScope
import org.hitchwiki.maps.data.SpotDetailSource
import org.hitchwiki.maps.ui.detail.SpotDetailScreen
import org.hitchwiki.maps.ui.detail.SpotDetailViewModel
import org.hitchwiki.maps.ui.map.MapScreen
import org.hitchwiki.maps.ui.map.MapViewModel

@Composable
fun AppNav(
    mapViewModel: MapViewModel,
    detailSource: SpotDetailSource,
    scope: CoroutineScope,
    onRequestLocation: () -> Unit,
) {
    val nav = rememberNavController()
    NavHost(nav, startDestination = "map") {
        composable("map") {
            MapScreen(
                viewModel = mapViewModel,
                onRequestLocation = onRequestLocation,
                onOpenDetail = { sid, rating, count -> nav.navigate("spot/$sid?rating=$rating&count=$count") },
            )
        }
        composable(
            route = "spot/{sid}?rating={rating}&count={count}",
            arguments = listOf(
                navArgument("sid") { type = NavType.StringType },
                navArgument("rating") { type = NavType.FloatType; defaultValue = 0f },
                navArgument("count") { type = NavType.IntType; defaultValue = 0 },
            ),
        ) { entry ->
            val sid = entry.arguments?.getString("sid") ?: return@composable
            val rating = entry.arguments?.getFloat("rating") ?: 0f
            val count = entry.arguments?.getInt("count") ?: 0
            // Fresh detail VM per navigation to this spot; remember it against the sid.
            val vm = androidx.compose.runtime.remember(sid) { SpotDetailViewModel(sid, detailSource, scope) }
            SpotDetailScreen(viewModel = vm, rating = rating, reviewCount = count, onBack = { nav.popBackStack() })
        }
    }
}
```

- [ ] **Step 3: Host `AppNav` from `MainActivity`**

In `MainActivity.kt`, keep the dependency-graph construction, and replace the `setContent { MaterialTheme { MapScreen(...) } }` block with `AppNav`:
```kotlin
        setContent {
            MaterialTheme {
                AppNav(
                    mapViewModel = viewModel,
                    detailSource = details,
                    scope = lifecycleScope,
                    onRequestLocation = { permissionLauncher.launch(Manifest.permission.ACCESS_FINE_LOCATION) },
                )
            }
        }
```
Add `import org.hitchwiki.maps.ui.AppNav`. (The `details` = `ApiSpotDetailSource(api)` already built in P2's MainActivity; reuse it. If the local val name differs, adapt.)

- [ ] **Step 4: Build**

Run: `cd mobile && ./gradlew :composeApp:assembleDebug`
Expected: BUILD SUCCESSFUL, APK produced. If `navigation-compose:2.8.0-alpha10` doesn't resolve or a `NavType`/`navArgument` API differs at that version, adapt to the resolved API (do NOT change the CMP/Kotlin version unilaterally) and note it.

- [ ] **Step 5: Full suite + iOS compile guard**

Run: `cd mobile && ./gradlew :composeApp:testDebugUnitTest :composeApp:compileKotlinIosSimulatorArm64`
Expected: BUILD SUCCESSFUL — all shared tests pass and iOS compiles (nav-compose is multiplatform; the detail UI + AppNav compile for iOS).

- [ ] **Step 6: Write the manual test steps (for the human) into the report**

In your report, give the exact commands the human runs (with an AVD already running):
```
cd mobile && ./gradlew :composeApp:installDebug
~/Library/Android/sdk/platform-tools/adb shell monkey -p org.hitchwiki.maps 1
```
Expected: tapping a marker opens a summary sheet with a ★ rating, review count, avg wait, and up to 3 ride cards; "Full detail" navigates to a full screen with the header stats, all ride cards, and tappable OSM/Hitchwiki link chips (open the browser); the system back button returns to the map.

- [ ] **Step 7: Commit**

```bash
git add mobile/gradle/libs.versions.toml mobile/composeApp/build.gradle.kts \
        mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/ui/AppNav.kt \
        mobile/composeApp/src/androidMain/kotlin/org/hitchwiki/maps/MainActivity.kt
git commit -m "feat(mobile): AppNav navigation graph; MainActivity hosts map + spot detail"
```

---

## Self-Review

**Spec coverage:**
- Summary sheet (rating+count, avg wait, last 3 rides, Full detail button) — Tasks 3 (rating/count), 6 ✓.
- Full-detail screen (header, all rides, link chips) — Tasks 4 (VM), 5 (cards), 7 ✓.
- Navigation (routes map/spot, args) — Task 8 ✓.
- Link chips with exact web URLs via LocalUriHandler — Tasks 1, 7 ✓.
- kotlinx-datetime dates — Task 2 ✓.
- Shared RideCard/RatingStars — Task 5 ✓.
- rating/count via nav args (per-spot JSON has no aggregate) — Tasks 6, 8 ✓.
- iOS compiles / MapLibre untouched — build guards in Tasks 5–8; P3b never imports MapLibre ✓.
- Deferred correctly absent: full-screen actions, P3a map polish, filters/search, recent list.

**Placeholder scan:** No "TBD". Version-sensitive spots (navigation-compose API at 2.8.0-alpha10, the lazy `items` import, the `ridesNewestFirst` comparator) carry explicit "verify against the resolved API / test confirms the ordering, adapt and report" instructions — the same transcription-fix pattern P1/P2 used, not open placeholders. The `MapViewModel`/`MainActivity` edits reference the real current signatures (read before writing).

**Type consistency:** `SpotLink`/`spotLinks`, `formatRideDate`, `ridesNewestFirst`, `SpotDetailUiState`/`SpotDetailViewModel(sid, details, scope)`/`.load()`, `RatingStars(rating: Int?)`, `RideCard(ride)`, `SpotSummarySheet(state, onDismiss, onOpenDetail)`, `MapScreen(..., onOpenDetail: (String,Float,Int)->Unit)`, `SpotDetailScreen(viewModel, rating, reviewCount, onBack)`, `AppNav(mapViewModel, detailSource, scope, onRequestLocation)` — consistent across every task. Existing symbols (`MapViewModel.selectSpot/clearSelection`, `MapUiState`, `ApiSpotDetailSource`, `SpotDetail`/`SpotInfo`/`OsmRef`/`SpotRide`, `spotId`) consumed as they exist.

---

## Notes for later phases
- **P3a** (map polish) still pending; its initial-camera edit also touches `MainActivity` — expect a small merge with this task's `MainActivity` change.
- **Later:** full-screen actions (share / open-in-maps), filters/search, recent-rides, rotation/resource retention (retained ViewModels — nav-compose makes this cleaner now), a11y, iOS map bring-up.
