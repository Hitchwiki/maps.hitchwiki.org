# Hitchwiki Maps — KMP App P2: Map + Spot Markers (Android) — Design

**Date:** 2026-07-14
**Status:** Approved design, ready for implementation planning
**Predecessors:** [v1 design](2026-07-14-kmp-app-v1-design.md), P0+P1 (scaffold + data layer, complete & green)

## Goal

Turn the placeholder app into the real product: a MapLibre map showing the live
hitchhiking spots. P2 delivers, on **Android** (iOS map stubbed but compiling):

- An **OSM vector basemap** via the OpenStreetMap US Tileservice (no API key).
- **All live spots** from `SpotRepository` (`maps.hitchwiki.org/spots.json`, ~35k) drawn
  as **clustered markers**.
- **Tap a marker** → load that spot's detail via the data layer → show a **minimal
  summary** (full detail sheet is P3).
- A **current-location** button and a sensible **initial camera**.
- Required **OpenStreetMap + OpenStreetMap US attribution**.

## Non-goals (P2)

- iOS map rendering (stub `actual`, keep the iOS target compiling).
- Offline tiles / PMTiles / downloaded regions — deferred to P6.
- Filters, search, the full spot-detail sheet, ride submission — P3+.
- Any Mapbox SDK. P2 stays on **MapLibre** (the P1 spike's `org.maplibre.gl:android-sdk:11.5.0`).

## Key decisions

| Decision | Choice |
|---|---|
| Map SDK | MapLibre (keep the spike); NOT Mapbox |
| Basemap | OSM US Tileservice — OpenMapTiles vector TileJSON, no key |
| Marker rendering | One MapLibre GeoJSON source with `cluster=true` (GPU clustering, handles 35k) |
| Marker color | By rating: green ≥4, amber =3, red ≤2; clusters = filled circle + count |
| Interaction | Tap → load `SpotDetail` → minimal summary; current-location FAB; initial camera |
| Platform | Android functional; iOS `actual` stubbed (keeps compiling) |
| Data | Live `maps.hitchwiki.org` via the P1 `SpotRepository` / `HitchwikiApi` |

## Basemap specifics

- **Vector tile source (TileJSON, no key):** `https://tiles.openstreetmap.us/vector/openmaptiles.json`
  (OpenMapTiles schema + Planetiler extensions, MapLibre-compatible, updated several times/day).
- **Full `style.json`:** bundle an open-source OpenMapTiles-schema style (e.g. OSM-Bright /
  Positron-style GL JSON) in app assets, with its `sources.openmaptiles.url` set to the
  TileJSON above and `glyphs` set to the OSM US fonts endpoint. (If OSM US publishes a
  ready-made hosted style.json, the plan may use it directly instead; the bundled-style path
  is the guaranteed-workable baseline so P2 is not blocked on confirming a hosted URL.)
- **Attribution (required):** show "© OpenStreetMap contributors, © OpenStreetMap US" per the
  OSM US usage policy, visible on the map.
- **Tier:** Starter tier (anonymous, rate-limited) is sufficient for development. Production
  scale would move to the OSM US Partner tier (recurring donation) or self-hosting — out of
  P2 scope, noted for later.

## Architecture — the `expect/actual` map seam

MapLibre is an Android-native library, so **`commonMain` must not reference it**. The boundary:

### commonMain (shared, unit-testable without a device)
- **`MapViewModel` + `MapUiState`** — owns the spot list (via `SpotRepository`), the selected
  spot's `SpotDetail` (via `HitchwikiApi.spotDetail`), the camera target, and
  location/permission state. Pure Kotlin + coroutines; testable against a fake repository.
- **`expect fun PlatformMap(state: MapState, callbacks: MapCallbacks, modifier: Modifier)`** —
  the platform map surface composable.
- **`expect class LocationProvider { suspend fun current(): LatLng? }`**.
- **`buildSpotsGeoJson(spots: List<Spot>): String`** — pure spots→GeoJSON FeatureCollection
  converter; each feature carries `lat`/`lon`/`rating` and a `sid` (derived via `spotId`) so a
  tapped feature maps back to its per-spot detail file. Unit-tested.
- **`MapScreen`** — a Compose Multiplatform composable that places `PlatformMap` and the overlay
  UI (attribution text, location FAB, minimal bottom sheet) and binds them to `MapViewModel`.

`MapState`/`MapCallbacks` are plain data types (the GeoJSON string or spot list, selected
`sid`, camera target, user location; callbacks `onSpotClick(sid)`, `onCameraIdle`,
`onMapReady`) — no MapLibre types cross into commonMain.

### androidMain (`actual`)
- **`PlatformMap`** = `AndroidView` hosting a MapLibre `MapView`; sets the OSM US style; adds one
  **GeoJSON source with `cluster = true`** feeding: a cluster `CircleLayer`, a cluster-count
  `SymbolLayer`, and an unclustered-point layer colored by `rating`. A map click runs
  `queryRenderedFeatures` at the tap point → if it hits a cluster, zoom to its expansion; if a
  point, read its `sid` and call `onSpotClick(sid)`.
- **`LocationProvider`** = fused/last-known location (Play Services or platform `LocationManager`).

### iosMain (`actual`)
- **`PlatformMap`** = empty `Box` + `// TODO(iOS bring-up): MapLibre iOS actual`.
- **`LocationProvider`** = stub returning `null`.
- Purpose: keep `iosSimulatorArm64` compiling (guarded in CI), nothing more.

## Data flow

1. Screen enters → `MapViewModel.load()` → `SpotRepository.spots()` (live, cached) →
   `buildSpotsGeoJson(spots)` → handed to `PlatformMap` → MapLibre clusters on the GPU.
2. Tap marker → `onSpotClick(sid)` → `MapViewModel.selectSpot(sid)` →
   `HitchwikiApi.spotDetail(sid)` → `MapUiState.selectedDetail` → Compose bottom sheet shows a
   **minimal summary** (avg wait, ride count, rating). Full sheet = P3.
3. Location FAB → request runtime permission → `LocationProvider.current()` → animate camera.
   Initial camera = last-known location if available, else a world/default view.

## New/changed files (under `mobile/composeApp`)
- `commonMain`: `ui/map/MapScreen.kt`, `ui/map/MapViewModel.kt`, `ui/map/MapUiState.kt`,
  `data/GeoJson.kt` (tested), `map/PlatformMap.kt` (expect), `location/LocationProvider.kt` (expect).
  Extend the data layer with a spot-detail fetch path (`HitchwikiApi.spotDetail` already exists;
  add a thin `SpotDetailRepository` or a `MapViewModel` call — no per-spot cache in P2).
- `androidMain`: `map/PlatformMap.android.kt` (MapLibre), `location/LocationProvider.android.kt`;
  add MapLibre dep (from the spike) to `androidMain`; add `INTERNET` + `ACCESS_FINE_LOCATION`/
  `ACCESS_COARSE_LOCATION` to the manifest; wire `MainActivity` → `MapScreen`.
- `iosMain`: `map/PlatformMap.ios.kt` (stub), `location/LocationProvider.ios.kt` (stub).

## Testing
- **commonTest (no device):** `buildSpotsGeoJson` output (feature count, coords, `sid`, `rating`
  properties); `MapViewModel` state transitions against a fake `SpotRepository`/detail source
  (load → spots present; `selectSpot` → detail loaded; location → camera target set);
  `spotId` round-trip from a tapped feature.
- **User-verified on an Android emulator (agent cannot run one):** basemap renders, markers
  cluster/uncluster across zoom, tap opens the summary, location button recenters.
- **iOS compile guard:** `./gradlew :composeApp:compileKotlinIosSimulatorArm64` stays green.

## Risks / known-unknowns
- **Clustering + tap hit-testing** in MapLibre Android (GeoJSON `cluster=true`,
  `queryRenderedFeatures`, cluster expansion zoom) is fiddlier than the basic render the P1 spike
  proved — the primary P2 integration risk. The plan front-loads a small clustering/tap spike.
- **Exact OSM US style.json** — mitigated by bundling an open-source OpenMapTiles-schema style
  pointed at the confirmed TileJSON; a hosted style may replace it if found.
- **spots.json size** (~35k points, a few MB) — fetch + GeoJSON build on device; expected fine,
  clustering covers render perf. Watch memory on low-end devices.
- **OSM US starter-tier rate limits** — fine for single-dev testing; production → Partner tier
  or self-host (later phase).
- **Location permission flow** in Compose Multiplatform on Android — standard but needs runtime
  request handling.

## Deferred to later phases
- iOS map bring-up (MapLibre iOS `actual`) — post-MVP.
- Offline tiles / PMTiles / region download UX — P6.
- Full spot-detail sheet, filters, search — P3.
- Production tile tier / self-hosting decision.
