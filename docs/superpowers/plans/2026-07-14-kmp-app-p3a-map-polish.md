# KMP App P3a — Map Polish + Load Instrumentation (Android) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the P2 map legible — place-name labels + cluster-count numbers + an initial camera on last-known location — and add lightweight first-load instrumentation so the deferred first-run crash leaves a trace if it recurs. Android only; iOS stays a compiling stub.

**Architecture:** Adding text (labels + cluster counts) reverses P2's "CircleLayers-only, no glyphs" choice, so the bundled style gains a **glyphs URL** and a place-name `SymbolLayer`, and `PlatformMap` gains a cluster-count `SymbolLayer`. Initial camera reuses the existing `LocationProvider` + `MapViewModel.onUserLocation`. Instrumentation is a default uncaught-exception handler + stage logging — **diagnostics only, no behavior change and no blind fix**.

**Tech Stack:** unchanged — Kotlin 2.1.0, Compose Multiplatform 1.7.3, MapLibre `org.maplibre.gl:android-sdk:11.5.0`. No new dependencies.

## Global Constraints

- **Slice-0 (`OsmRef` model fix) already landed** (commit 287b2cf) — not part of this plan.
- **MapLibre only in androidMain**; iOS `PlatformMap` stub untouched; `compileKotlinIosSimulatorArm64` stays green.
- **Glyphs source:** `https://tiles.openstreetmap.us/fonts/{fontstack}/{range}.pbf`; font stack `"Noto Sans Regular"` (standard OpenMapTiles). If labels don't render (glyphs 404), fall back to `https://fonts.openmaptiles.org/{fontstack}/{range}.pbf` and/or the exact stack the endpoint serves — verify on the emulator and record what worked.
- **The instrumentation is NOT a crash fix.** The first-run crash has no captured root cause (see the P3a spec / debugging notes). Do not change load/save/GeoJSON behavior to "fix" it — only add logging + a passthrough uncaught-exception handler that logs then delegates to the previous handler.
- **Marker CircleLayers from P2 stay**; the cluster-count SymbolLayer is drawn on top of the cluster circles.
- Verification is build + a named on-device check (map/UI); commit each task. Package root `org.hitchwiki.maps`.

---

## Task 1: First-load instrumentation (diagnostics only)

**Files:**
- Modify: `mobile/composeApp/src/androidMain/kotlin/org/hitchwiki/maps/MainActivity.kt`
- Modify: `mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/ui/map/MapViewModel.kt`
- Modify: `mobile/composeApp/src/androidMain/kotlin/org/hitchwiki/maps/map/PlatformMap.android.kt`

**Interfaces:** No API changes. Adds logging + an uncaught-exception passthrough handler.

- [ ] **Step 1: Uncaught-exception handler in MainActivity**

At the very top of `MainActivity.onCreate` (before building the graph), add a handler that logs any uncaught throwable (from any thread) with its full stack, then delegates to the previous handler so app behavior is unchanged:
```kotlin
val prev = Thread.getDefaultUncaughtExceptionHandler()
Thread.setDefaultUncaughtExceptionHandler { thread, throwable ->
    android.util.Log.e("HitchwikiCrash", "Uncaught on ${thread.name}", throwable)
    prev?.uncaughtException(thread, throwable)
}
```

- [ ] **Step 2: Stage logging in `MapViewModel.load()`**

`MapViewModel` is commonMain (no `android.util.Log`). Add stage logging via `println` (which reaches logcat on Android as `System.out`) inside `load()` — before fetch, after fetch (count), after geojson build (length), and in the catch. Example (keep the existing logic; only add the log lines):
```kotlin
fun load() {
    _state.update { it.copy(loading = true, error = null) }
    scope.launch {
        try {
            println("HitchwikiLoad: fetching spots")
            val fresh = spots.spots()
            println("HitchwikiLoad: got ${fresh.size} spots")
            val geo = buildSpotsGeoJson(fresh)
            println("HitchwikiLoad: built geojson len=${geo.length}")
            spotsBySid = fresh.associateBy { org.hitchwiki.maps.util.spotId(it.lat, it.lon) }
            _state.update { it.copy(loading = false, spots = fresh, geoJson = geo) }
            println("HitchwikiLoad: state updated")
        } catch (e: Throwable) {
            println("HitchwikiLoad: FAILED ${e::class.simpleName}: ${e.message}")
            _state.update { it.copy(loading = false, error = e.message ?: "Failed to load spots") }
        }
    }
}
```
(A native crash won't hit the catch, but the last `println` before death localizes where it died — e.g. crash after "built geojson" but before "state updated" points at the MapLibre `setGeoJson` hand-off.)

- [ ] **Step 3: Log around the GeoJSON hand-off in `PlatformMap` update**

In `PlatformMap.android.kt`'s `update` block, log immediately before and after the guarded `setGeoJson` call so a native crash during MapLibre's parse of the ~35k-feature source is bracketed:
```kotlin
if (lastPushed.value != state.geoJson) {
    android.util.Log.d("HitchwikiMap", "setGeoJson len=${state.geoJson.length}")
    m.style?.getSourceAs<GeoJsonSource>(SRC)?.setGeoJson(state.geoJson)
    lastPushed.value = state.geoJson
    android.util.Log.d("HitchwikiMap", "setGeoJson done")
}
```

- [ ] **Step 4: Build both targets**

Run: `cd mobile && ./gradlew :composeApp:assembleDebug :composeApp:compileKotlinIosSimulatorArm64`
Expected: BUILD SUCCESSFUL. Also run the full unit suite to confirm the `MapViewModel` edit didn't break tests: `cd mobile && ./gradlew :composeApp:testDebugUnitTest` → all pass.

- [ ] **Step 5: Commit**

```bash
git add mobile/composeApp/src/androidMain/kotlin/org/hitchwiki/maps/MainActivity.kt \
        mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/ui/map/MapViewModel.kt \
        mobile/composeApp/src/androidMain/kotlin/org/hitchwiki/maps/map/PlatformMap.android.kt
git commit -m "chore(mobile): first-load instrumentation (uncaught handler + stage logs)"
```

---

## Task 2: Glyphs URL + place-name labels

**Files:**
- Modify: `mobile/composeApp/src/androidMain/assets/osm_us_style.json`

**Interfaces:** Adds a top-level `glyphs` and a place-name `SymbolLayer` to the style.

- [ ] **Step 1: Add glyphs + a place-labels symbol layer**

Add a top-level `"glyphs"` key and append a place `SymbolLayer` as the LAST entry of `layers` (so labels draw above the fills/lines; the programmatic marker layers still draw above that):
```json
  "glyphs": "https://tiles.openstreetmap.us/fonts/{fontstack}/{range}.pbf",
```
and in `layers`, after `building`:
```json
    { "id": "place-labels", "type": "symbol", "source": "openmaptiles", "source-layer": "place",
      "filter": ["in", "class", "city", "town", "village"],
      "layout": { "text-field": "{name}", "text-font": ["Noto Sans Regular"], "text-size": 12, "text-max-width": 8 },
      "paint": { "text-color": "#3a3a3a", "text-halo-color": "#ffffff", "text-halo-width": 1.2 } }
```
(`glyphs` goes at the same object level as `sources`/`layers`.)

- [ ] **Step 2: Build**

Run: `cd mobile && ./gradlew :composeApp:assembleDebug`
Expected: BUILD SUCCESSFUL (the asset is just JSON; this mainly repackages).

- [ ] **Step 3: On-device check (human)**

Install and open the app; zoom into a populated region. Expected: city/town/village **names render** over the map. If labels are missing (glyphs 404 for "Noto Sans Regular"), switch `glyphs` to `https://fonts.openmaptiles.org/{fontstack}/{range}.pbf` and/or adjust `text-font` to a stack the endpoint serves, rebuild, and confirm. Record what worked in the report.

- [ ] **Step 4: Commit**

```bash
git add mobile/composeApp/src/androidMain/assets/osm_us_style.json
git commit -m "feat(mobile): OSM US glyphs + place-name labels on the basemap"
```

---

## Task 3: Cluster-count numbers (SymbolLayer)

**Files:**
- Modify: `mobile/composeApp/src/androidMain/kotlin/org/hitchwiki/maps/map/PlatformMap.android.kt`

**Interfaces:** Adds a `SymbolLayer` (id `spots-cluster-count`) filtered to clusters, drawing `point_count_abbreviated` in white over the cluster circles. Depends on Task 2's glyphs.

- [ ] **Step 1: Add the imports + layer id**

Add imports `org.maplibre.android.style.layers.SymbolLayer` and `org.maplibre.android.style.layers.PropertyFactory` (PropertyFactory is likely already imported). Add `private const val LYR_CLUSTER_COUNT = "spots-cluster-count"` near the other layer-id constants.

- [ ] **Step 2: Add the cluster-count SymbolLayer**

Immediately AFTER the cluster `CircleLayer` is added (so text draws on top of the circles), add:
```kotlin
style.addLayer(
    SymbolLayer(LYR_CLUSTER_COUNT, SRC).apply {
        setFilter(Expression.has("point_count"))
        setProperties(
            PropertyFactory.textField(Expression.toString(Expression.get("point_count_abbreviated"))),
            PropertyFactory.textFont(arrayOf("Noto Sans Regular")),
            PropertyFactory.textSize(12f),
            PropertyFactory.textColor(android.graphics.Color.WHITE),
            PropertyFactory.textAllowOverlap(true),
            PropertyFactory.textIgnorePlacement(true),
        )
    },
)
```
Use the same font stack that Task 2 confirmed works. If a MapLibre 11.5.0 symbol/expression signature differs (`textField`, `Expression.toString`), adapt to the resolved API and note it.

- [ ] **Step 3: Build + iOS compile guard**

Run: `cd mobile && ./gradlew :composeApp:assembleDebug :composeApp:compileKotlinIosSimulatorArm64`
Expected: BUILD SUCCESSFUL.

- [ ] **Step 4: On-device check (human)**

Open the app; the blue cluster circles should now show a **white count number** (e.g. "1.2k", "340"). Tapping still zooms in. Record confirmation.

- [ ] **Step 5: Commit**

```bash
git add mobile/composeApp/src/androidMain/kotlin/org/hitchwiki/maps/map/PlatformMap.android.kt
git commit -m "feat(mobile): cluster-count numbers on the map"
```

---

## Task 4: Initial camera to last-known location

**Files:**
- Modify: `mobile/composeApp/src/androidMain/kotlin/org/hitchwiki/maps/MainActivity.kt`

**Interfaces:** On start, if location permission is already granted, center the map on last-known location (no prompt). Reuses `LocationProvider` + `MapViewModel.onUserLocation`.

- [ ] **Step 1: Read the current MainActivity**

Read `MainActivity.kt` first (it builds the graph, `viewModel`, `locationProvider`, `permissionLauncher`, hosts `AppNav`). Confirm the local val names before editing.

- [ ] **Step 2: Add the permission-gated initial-location fetch**

After the graph is built (so `viewModel` and `locationProvider` exist) and before/after `setContent`, add:
```kotlin
// Initial camera: if location permission is ALREADY granted, center on last-known location
// without prompting (the FAB still owns the request flow). Otherwise the map opens at its
// default world view.
val hasLoc = androidx.core.content.ContextCompat.checkSelfPermission(
        this, Manifest.permission.ACCESS_FINE_LOCATION) == android.content.pm.PackageManager.PERMISSION_GRANTED ||
    androidx.core.content.ContextCompat.checkSelfPermission(
        this, Manifest.permission.ACCESS_COARSE_LOCATION) == android.content.pm.PackageManager.PERMISSION_GRANTED
if (hasLoc) {
    lifecycleScope.launch { locationProvider.current()?.let { viewModel.onUserLocation(it) } }
}
```
(`Manifest` and `lifecycleScope` are already imported/used in MainActivity from P2/P3b. Add the `ContextCompat`/`PackageManager` references as fully-qualified above or import them.) The `onUserLocation` sets `cameraTarget`; the map's `update` block consumes it once the map is ready (even if set before the map finishes initializing — the mapRef transition re-runs `update`).

- [ ] **Step 3: Build**

Run: `cd mobile && ./gradlew :composeApp:assembleDebug :composeApp:compileKotlinIosSimulatorArm64`
Expected: BUILD SUCCESSFUL.

- [ ] **Step 4: On-device check (human)**

First grant location once (tap ◎, allow). Then relaunch the app: it should **open centered on your location** rather than the world view. (Before granting, it opens at world view — no prompt on launch.) Record confirmation.

- [ ] **Step 5: Commit**

```bash
git add mobile/composeApp/src/androidMain/kotlin/org/hitchwiki/maps/MainActivity.kt
git commit -m "feat(mobile): open the map on last-known location when permission is granted"
```

---

## Self-Review

**Spec coverage (P3a spec):**
- Slice-0 model fix — already landed (287b2cf), not in this plan ✓.
- Place-name labels (glyphs + SymbolLayer) — Task 2 ✓.
- Cluster-count numbers — Task 3 ✓ (depends on Task 2's glyphs; ordered correctly).
- Initial camera to last-known location, permission-gated, no launch prompt — Task 4 ✓.
- Load instrumentation for the deferred crash (chosen addition) — Task 1 ✓ (diagnostics only, explicitly not a fix).
- iOS stays a compiling stub; MapLibre stays in androidMain — build guards in every task ✓.

**Placeholder scan:** No "TBD". The version-sensitive spots (the OSM US fontstack name; MapLibre 11.5.0 `SymbolLayer`/`textField`/`Expression.toString`) carry explicit verify-and-adapt-and-report instructions with a concrete glyphs fallback — the same pattern P2/P3b used. The instrumentation is bounded to logging + a passthrough handler.

**Type consistency:** No new public API. Edits reference existing symbols (`MapViewModel.load`/`onUserLocation`, `LocationProvider.current`, `GeoJsonSource`, `SRC`/`LYR_CLUSTER`, `spotId`) as they exist. Task 4 reads MainActivity's real local names before editing.

**Discipline note:** Task 1 is diagnostics, NOT a fix for the unreproduced first-run crash. The actual fix waits for a captured trace (uncaught handler / stage logs will provide it on recurrence).

---

## Notes for later phases
- **First-run crash:** still open, deferred with no confirmed root cause. Task 1's instrumentation should surface a trace on the next cold-start recurrence; fix then, with evidence.
- **Later:** full-screen actions, filters/search, recent-rides, rotation/resource retention (retained ViewModels), a11y, iOS map bring-up.
