# Hitchwiki Maps — KMP App P3a: Model Fix + Map Polish (Android) — Design

**Date:** 2026-07-14
**Status:** Approved design, ready for implementation planning
**Predecessors:** [v1](2026-07-14-kmp-app-v1-design.md), P0/P1 (data layer), [P2 map](2026-07-14-kmp-app-p2-map-design.md) — all complete & green.

P3 was split into **P3a** (this doc — model fix + map polish) and **P3b** (the two-tier
detail UX + navigation, a separate later spec).

## Goal

Two things, on **Android** (iOS map stays a compiling stub):

1. **Slice 0 — fix a live crash.** `SpotInfo.carPooling`/`fuel` are typed `String?` but the
   backend emits objects `{"id": int, "osm_type": str}`. With strict JSON (P1 dropped
   `isLenient`), `spotDetail()` **throws** for any spot near a car-pooling spot or gas station.
   Retype them and add a guarding test. Ships independently, first.
2. **Map polish** — make the P2 map legible: place-name labels + cluster-count numbers, and an
   initial camera on last-known location.

## Non-goals (P3a)

- The detail UX (summary sheet, full-detail screen, navigation) — that's **P3b**.
- iOS map rendering (stub stays).
- Filters/search, recent-rides list, rotation/resource retention, a11y polish — later.

## Key decisions

| Decision | Choice |
|---|---|
| car_pooling/fuel model | `@Serializable data class OsmRef(id: Long, osmType: String)` (was `String?`) |
| Labels | Add a **glyphs URL** + a place-name `SymbolLayer` to the bundled style |
| Cluster counts | A `SymbolLayer` with `point_count_abbreviated`, added beside the cluster circles |
| Glyphs source | `https://tiles.openstreetmap.us/fonts/{fontstack}/{range}.pbf` (fallback: `fonts.openmaptiles.org`) |
| Initial camera | Last-known location **only if permission already granted** (no prompt); else default view |
| Platform | Android functional; iOS stub unaffected |

This **reverses P2's deliberate "CircleLayers-only, no glyphs" simplification** — adding
SymbolLayers means the style now needs a working glyphs URL.

## Slice 0 — model fix (standalone, first)

- `mobile/composeApp/src/commonMain/kotlin/org/hitchwiki/maps/model/SpotDetail.kt`:
  add `@Serializable data class OsmRef(val id: Long, @SerialName("osm_type") val osmType: String)`;
  change `SpotInfo.carPooling: String?` → `OsmRef?` and `SpotInfo.fuel: String?` → `OsmRef?`.
  `osmId: Long?`, `hitchwikiArticle`/`hitchwikiMap: String?` are unchanged (already correct).
- Test: parse a per-spot fixture whose `spot` includes `"car_pooling":{"id":123,"osm_type":"way"}`
  and `"fuel":{"id":45,"osm_type":"node"}`; assert both parse into `OsmRef`. This test fails
  against the current `String?` model (strict JSON throws), so it guards the fix.
- Independently landable/reviewable; it also unblocks the correct rendering of the link chips in P3b.

## Map polish

### Place-name labels
- Add `"glyphs": "https://tiles.openstreetmap.us/fonts/{fontstack}/{range}.pbf"` to
  `assets/osm_us_style.json`.
- Add a place-name `SymbolLayer` sourcing the `place` source-layer: `text-field` = `{name}`,
  `text-font` = a stack OSM US serves (confirm the exact name, default `["Noto Sans Regular"]`),
  a small `text-size`, and a filter to sensible place classes (city/town/village) so low zooms
  aren't cluttered. The plan pins the exact fontstack after checking the fonts endpoint.

### Cluster-count numbers
- Add a `SymbolLayer` on the spots source filtered to `has("point_count")`, `text-field` =
  `Expression.toString(Expression.get("point_count_abbreviated"))`, `text-font` the same stack,
  white text centered over the existing cluster circles. (Circles from P2 stay; this adds the count.)

### Initial camera
- On app start, if `ACCESS_FINE_LOCATION`/`COARSE` is **already granted**, call
  `LocationProvider.current()` and feed it to `MapViewModel.onUserLocation(...)` so the map opens
  centered on the user — **without triggering a permission prompt** (the FAB still handles the
  request flow). If not granted or no fix, keep a sensible default camera (e.g. a mid-latitude
  world view) rather than MapLibre's (0,0) zoom-0 default.

## New/changed files (`mobile/composeApp`)
- `model/SpotDetail.kt` — `OsmRef` + retype (Slice 0).
- `commonTest/.../model/SpotDetailTest.kt` — add the car_pooling/fuel object case.
- `androidMain/assets/osm_us_style.json` — add `glyphs` + place-name SymbolLayer.
- `androidMain/.../map/PlatformMap.android.kt` — add the cluster-count SymbolLayer.
- `androidMain/.../MainActivity.kt` — startup last-known-location camera (permission-gated, no prompt).

## Testing
- **commonTest (headless):** the Slice-0 parsing test (car_pooling/fuel objects). (Labels /
  cluster counts / camera are MapLibre + Android runtime — not headless-unit-testable.)
- **User-verified on emulator:** place labels render at appropriate zooms; cluster circles now
  show counts; the map opens on the user's location when permission is already granted (else a
  default view, no prompt on launch).
- **iOS compile guard** stays green.

## Risks / known-unknowns
- **Exact fontstack name** OSM US serves (e.g. "Noto Sans Regular") — the plan verifies against
  the fonts endpoint; if a label layer references a missing fontstack, glyphs 404 and text
  silently doesn't render. Fallback: `https://fonts.openmaptiles.org/{fontstack}/{range}.pbf`.
- **Label density/clutter** — needs a zoom/class filter tuned by eye (user-verified).
- **Startup location without a prompt** — only read last-known when permission is already held;
  never request on launch (that belongs to the FAB flow).

## Deferred (P3b and beyond)
- Two-tier detail UX (summary sheet + full-detail screen) + JetBrains Compose Navigation — **P3b**.
- Filters/search, recent-rides list, rotation/resource retention, a11y, iOS map.
