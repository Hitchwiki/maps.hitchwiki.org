# Hitchwiki Maps — KMP App P3c: Filters, Search & Recent (Android) — Design

**Date:** 2026-07-14
**Status:** Approved design, ready for implementation planning
**Predecessors:** P0/P1 (data), [P2 map](2026-07-14-kmp-app-p2-map-design.md),
[P3a map polish](2026-07-14-kmp-app-p3a-map-polish-design.md),
[P3b detail UX](2026-07-14-kmp-app-p3b-detail-ux-design.md).

## Goal

Complete the **P3 UI** milestone from the [v1 design](2026-07-14-kmp-app-v1-design.md) on
**Android** by adding the two remaining pieces — **filters** and **search / recent-rides** —
on top of the existing map + spot-detail experience. The shared UI compiles for iOS, but the
map stays a stub; only Android is run/tested.

- **Filter the map** by rating and spot flags, correctly under clustering.
- **Search + Recent** in one screen: an empty query shows the latest rides; typing filters them
  by hitchhiker name and comment. Tapping a result flies the map to that spot.

## Non-goals (P3c)

- Full-history search (all rides). v1 search covers the latest ~1000 rides only.
- A server-side search endpoint (no backend change in this slice).
- The broader load-perf slice (cache-first spot loading, network-first-every-launch policy,
  streaming). Only the one targeted `buildSpotsGeoJson` speedup below is in scope.
- Auth / ride submission (P4/P5), offline PMTiles packs (P6), iOS map.

## Key decisions

| Decision | Choice |
|---|---|
| Entry points | Pinned **top search bar** on the map + a **⚙ filter icon**; map stays home |
| Search screen | New `search` route: text field + results; **empty query → Recent list** |
| Search data | `spots_recent.json` (latest 1000 rides, ~397 KB); filter by **name + comment** |
| Search load | **Lazy** — fetched only when the search screen opens, never on map startup |
| Result tap | Pop to map → `MapViewModel.focusSpot(lat, lon, sid)` → camera fly + summary sheet |
| Filters | `min rating` (Any/3+/4+/5) + flag toggles **OSM · Hitchwiki · car-pooling · fuel** |
| Filter mechanism | Filter the in-memory `Spot` list → **rebuild the clustered GeoJSON source** (off-main) |
| Enabling change | Rewrite `buildSpotsGeoJson` to direct `StringBuilder` output (~12 s → sub-second) |
| Platform | Android functional; shared UI compiles for iOS; `PlatformMap` stays stubbed |

## Why rebuild, not a layer filter

The spots source is a **clustered** `GeoJsonSource`. MapLibre aggregates points into clusters at
the source level, *before* any layer `filter` runs, so a layer-filter expression hides individual
unclustered points but cannot correct cluster counts — at zoomed-out levels clusters would still
count filtered-out spots. Correct filtering therefore rebuilds the source from the filtered subset.
That rebuild must be fast, which is why the `buildSpotsGeoJson` speedup is part of this slice
rather than a separate perf task.

## Enabling change — fast `buildSpotsGeoJson`

`buildSpotsGeoJson` currently builds a `kotlinx.serialization` `JsonObject` tree per feature and
`toString()`s it — ~12 s for 35 k features (measured on-device: `got 35021 spots` → `built geojson`
≈ 12 s). Rewrite it to append directly to a `StringBuilder` (same output: a FeatureCollection of
`Point` features at `[lon, lat]` with `sid` and `rating` properties; numbers and the `sid` string
escaped/formatted identically). Expected result: sub-second, which (a) makes interactive filter
rebuilds viable and (b) removes ~12 s from the cold-load latency as a bonus. No behavioral change to
the map — the Android actual still feeds the returned String straight into `GeoJsonSource`.

## Components (`mobile/composeApp`, mostly commonMain)

### Filters
- `ui/map/FilterState.kt` — data class: `minRating: Int` (0 = Any) + `osm/wiki/cp/fuel: Boolean`;
  an `isActive` convenience.
- `data/SpotFilter.kt` — **pure** `applyFilters(spots: List<Spot>, state: FilterState): List<Spot>`
  (rating `>=` threshold; each enabled flag required). Testable in isolation.
- `ui/map/FilterSheet.kt` — a `ModalBottomSheet`: a rating segmented control + flag switches + a
  Reset action. Opened by the ⚙ icon; edits are pushed to `MapViewModel.setFilter`.
- `MapViewModel` additions:
  - Holds the full `spots` list (unchanged) plus `filterState`.
  - `setFilter(state)` → recompute `applyFilters` in memory, rebuild GeoJSON **off the main
    thread** (reuse the existing `workDispatcher`), update `geoJson`. `spotsBySid` stays keyed on
    the **full** set so `focusSpot` works even for a currently-filtered-out spot.
  - `focusSpot(lat, lon, sid)` → set `cameraTarget = LatLng(lat, lon)` and call `selectSpot(sid)`.
  - `MapUiState` gains `filterState: FilterState`.

### Search + Recent
- `model/RecentRide.kt` — `@Serializable` over `spots_recent.json` records
  (`url, submission_time, hitchhiker_name, rating, distance, text`). Derives `lat`/`lon` by parsing
  the `#<lat>,<lon>` `url` fragment and `sid` via `util.spotId(lat, lon)`. A malformed/short url
  yields a null-coordinate entry that is simply skipped (never crashes the list).
- `data/RecentRidesSource.kt` — interface + `ApiRecentRidesSource` calling
  `HitchwikiApi.recentRides()` (`GET /spots_recent.json`). Lazy: constructed with the graph but
  only invoked when the search screen mounts.
- `ui/search/SearchViewModel.kt` — plain-class VM (same pattern as `MapViewModel`): loads recent
  once, holds `query`, exposes `results` (empty query → all; else name/comment case-insensitive
  substring), plus loading/error/empty state.
- `ui/search/SearchScreen.kt` — `TextField` + a lazy list of result rows; empty/loading/error
  states; a row tap invokes `onResult(lat, lon, sid)`.
- `ui/common/RecentRideRow.kt` — one result row (name, rating stars, truncated comment, distance/
  date) — recent records have a different shape than `SpotDetail` rides, so this is a small
  dedicated row rather than reusing `RideCard`.

### Wiring
- `ui/map/MapScreen.kt` — add the pinned top search bar (tap → `onOpenSearch`) with the ⚙ filter
  icon (toggles the `FilterSheet`); keep the location FAB and summary sheet.
- `ui/AppNav.kt` — add `composable("search")` → `SearchScreen`; its `onResult` pops back to `map`
  and calls `mapViewModel.focusSpot(...)`. Add `onOpenSearch = { nav.navigate("search") }` to the
  map destination.
- `HitchwikiApi.kt` — add `recentRides(): List<RecentRide>`.

## Data flow

```
spots.json  ──(P1/P2, eager)──▶ MapViewModel.spots ──applyFilters(filterState)──▶ subset
                                                          │
                                       buildSpotsGeoJson (StringBuilder, off-main)
                                                          ▼
                                          MapUiState.geoJson ──▶ PlatformMap source

spots_recent.json ──(lazy, on search open)──▶ SearchViewModel.recent
        │                                            │
        │                                   query filter (name+comment)
        ▼                                            ▼
   RecentRide(lat,lon,sid)                    SearchScreen results
                                                     │ tap
                                                     ▼
                              nav pop → MapViewModel.focusSpot(lat,lon,sid)
                                     → cameraTarget + selectSpot → summary sheet
```

## Testing

**commonTest (headless):**
- `RecentRide`: `#<lat>,<lon>` url → `lat`/`lon`/`sid`; a short/garbled url → skipped, no throw.
- Search filter: name substring, comment substring, case-insensitivity, empty query → all.
- `applyFilters`: rating threshold (Any/3+/4+/5) and each flag (osm/wiki/cp/fuel), including
  combined flags; `isActive`.
- `buildSpotsGeoJson`: output is a valid FeatureCollection with the right feature count and each
  feature's `sid`/`rating`; a filtered-subset input yields exactly that subset (the rebuild path).
- `MapViewModel`: `setFilter` narrows `geoJson` to the subset (deterministic via the injected
  `workDispatcher`); `focusSpot` sets `cameraTarget` and the selection.
- `SearchViewModel`: load → recent populated; query → filtered; source failure → error, not stuck.

**Android on-device (human):** search bar → search screen; empty shows Recent; typing filters;
tap a result → map flies to the spot and its summary sheet opens; ⚙ → filter sheet; rating/flag
changes visibly narrow the markers (including cluster counts); Reset restores all.

**iOS compile guard** (`compileKotlinIosSimulatorArm64`) stays green — all new code is common Compose
/ data; only `PlatformMap` remains a stub.

## Risks / known-unknowns

- **`buildSpotsGeoJson` correctness after the rewrite** — the direct-string version must escape the
  `sid` and format doubles so MapLibre parses identically. Covered by the output-equivalence test
  and the on-device render check.
- **Filter rebuild latency** — after the speedup a full 35 k rebuild should be sub-second off-main;
  if it is still janky, debounce filter edits before rebuilding. Verified on-device.
- **`spots_recent.json` `url` format** — assumed `#<lat>,<lon>`; the parser must tolerate other
  shapes by skipping rather than crashing (tested).
- **Search bar over the map** — must sit above the map surface and inset for the status bar without
  blocking marker taps; on-device check.

## Deferred

Full-history / server search; offline packs; auth/write; iOS map; the broader load-perf slice
beyond the `buildSpotsGeoJson` speedup.
