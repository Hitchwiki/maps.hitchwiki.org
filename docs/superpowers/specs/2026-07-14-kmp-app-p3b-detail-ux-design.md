# Hitchwiki Maps — KMP App P3b: Two-Tier Spot Detail UX (Android) — Design

**Date:** 2026-07-14
**Status:** Approved design, ready for implementation planning
**Predecessors:** P0/P1 (data), [P2 map](2026-07-14-kmp-app-p2-map-design.md), P3a Slice-0
(the `OsmRef` model fix, already landed — commit 287b2cf). P3a map polish is a separate,
still-pending slice; P3b does not depend on it.

## Goal

Turn the P2 minimal tap-summary into a two-tier detail experience, on **Android** (iOS map
stays a compiling stub, but the shared detail UI compiles for iOS):

- **Tap a marker → summary sheet:** rating + review count, avg wait, the **last 3 rides**, and a
  **"Full detail"** button.
- **Full detail → dedicated screen:** header stats, **all** ride cards, and the OSM / car-pooling
  / gas / Hitchwiki **link chips** (informational only). System back returns to the map.
- Introduce **navigation** (JetBrains Compose Multiplatform `navigation-compose`) — the app's
  first multi-screen structure, so filters/recent/submission screens can slot in later.

## Non-goals (P3b)

- Actions on the full screen (share, open-in-maps, directions) — deferred.
- P3a map polish (labels, cluster counts, initial camera) — separate slice.
- Filters/search, recent-rides list, rotation/resource retention, a11y, iOS map.

## Key decisions

| Decision | Choice |
|---|---|
| Navigation | JetBrains Compose Multiplatform `navigation-compose`; routes `map`, `spot/{sid}` |
| Detail data | Full screen fetches `SpotDetail` by `sid`; `rating`/`count` passed as nav args |
| Full screen | Informational only (stats + all rides + link chips); no actions |
| Summary sheet | rating+count, avg wait, last 3 rides (newest-first), "Full detail" button |
| Links | Same URLs/labels as the web, opened via Compose `LocalUriHandler` |
| Dates | `kotlinx-datetime` → month-name ("January 2024") |
| Platform | Android functional; shared detail UI + nav compile for iOS; `PlatformMap` still stubbed |

## Navigation

- Add `org.jetbrains.androidx.navigation:navigation-compose` (multiplatform). The plan pins the
  exact version compatible with Compose Multiplatform 1.7.3 / Kotlin 2.1.0 (known-unknown; the
  plan verifies against the CMP↔nav compatibility table).
- New common `AppNav` composable owns a `NavHost(startDestination = "map")`:
  - `composable("map")` → `MapScreen(...)`, whose summary sheet's "Full detail" button calls
    `navController.navigate("spot/$sid?rating=$r&count=$c")`.
  - `composable("spot/{sid}?rating={rating}&count={count}")` → `SpotDetailScreen(sid, rating, count)`.
- `MainActivity` hosts `AppNav` (instead of `MapScreen` directly), building the P1/P2 dependency
  graph as before and passing what each screen needs.
- `sid` (e.g. `51.08170_13.73629`) is a single path segment (no slash), safe unencoded; `rating`
  (Float) and `count` (Int) are query args. They come from the marker (the per-spot JSON has no
  aggregate rating), so they must be threaded through, not re-derived on the detail screen.

## Summary sheet (replaces P2's minimal sheet)

- `ui/map/SpotSummarySheet.kt` — the expandable `ModalBottomSheet`, showing: **★ rating +
  review count**, **avg wait** (`SpotDetail.spot.wait`), the **last 3 rides** (newest-first by
  `submission_time`), and a **"Full detail"** button.
- `MapViewModel` change: when a marker is tapped, also expose the tapped `Spot`'s
  `rating`/`reviewCount`. Build a `sid → Spot` map once when `spots` load (avoid an O(35k) scan
  per tap); on `selectSpot(sid)` look it up and store `selectedRating`/`selectedReviewCount` in
  state. No extra network fetch — the marker already carries these.

## Full-detail screen (informational only)

- `ui/detail/SpotDetailScreen.kt` + `ui/detail/SpotDetailViewModel.kt`. The VM takes `sid` +
  `SpotDetailSource` + a `CoroutineScope` (same plain-class pattern as `MapViewModel`, not
  `androidx.lifecycle.ViewModel`), fetches the full `SpotDetail`, and exposes loading/error/data.
- Renders:
  - **Header:** ★ rating + review count (from nav args), avg wait + avg distance (from
    `SpotDetail.spot`).
  - **All ride cards** (newest-first): ★ rating, hitchhiker name, formatted date, wait, distance,
    comment. (Per-spot files already contain only informative rides.)
  - **Link chips** from `spotLinks(SpotInfo)`:
    - 🚏 Official hitchhiking spot → `https://www.openstreetmap.org/node/{osmId}`
    - 🚗 Car pooling spot → `https://www.openstreetmap.org/{carPooling.osmType}/{carPooling.id}`
    - ⛽ Gas station → `https://www.openstreetmap.org/{fuel.osmType}/{fuel.id}`
    - 📄 Mentioned on Hitchwiki → `{hitchwikiArticle}`
    - 🗺️ On Hitchwiki → `{hitchwikiMap}`
    Each opened via `LocalUriHandler`; absent links omitted.
  - Loading / error / empty ("No rides logged here yet") states.

## Shared pieces (commonMain)

- `data/SpotLinks.kt` — **pure, testable** `spotLinks(SpotInfo): List<SpotLink(emoji, label, url)>`
  + the URL builders. Correct now that `OsmRef` exists (P3a Slice-0).
- `util/RideDate.kt` — parse an ISO timestamp and format for display via `kotlinx-datetime`.
- `ui/common/RideCard.kt` + `ui/common/RatingStars.kt` — shared by the summary (take 3) and the
  full screen (all).

## New/changed files (`mobile/composeApp`, mostly commonMain)
- `ui/AppNav.kt` (new), `ui/map/SpotSummarySheet.kt` (new), `ui/detail/SpotDetailScreen.kt` +
  `SpotDetailViewModel.kt` (new), `ui/common/RideCard.kt` + `RatingStars.kt` (new),
  `data/SpotLinks.kt` (new), `util/RideDate.kt` (new).
- `ui/map/MapScreen.kt` — swap the inline minimal sheet for `SpotSummarySheet`; expose an
  `onOpenDetail(sid, rating, count)` callback.
- `ui/map/MapViewModel.kt` + `MapUiState.kt` — `sid→Spot` map + `selectedRating`/`selectedReviewCount`.
- `MainActivity.kt` — host `AppNav`; wire nav ↔ dependency graph.
- `gradle/libs.versions.toml` + `composeApp/build.gradle.kts` — add `navigation-compose` and
  `kotlinx-datetime`.

## Testing
- **commonTest (headless):** `spotLinks()` exact URLs + absent-link omission; `RideDate`
  formatting; `SpotDetailViewModel` state (fetch→detail / error / empty) against a fake source;
  `MapViewModel` selected-rating/count lookup by `sid`; the summary "last 3" selection + sort order.
- **User-verified on emulator:** summary sheet content, "Full detail" navigation + **system
  back**, full-screen content, link chips open the browser.
- **iOS compile guard** (`compileKotlinIosSimulatorArm64`) stays green — nav + detail UI are
  common Compose; only `PlatformMap` remains a stub.

## Risks / known-unknowns
- **`navigation-compose` version** for CMP 1.7.3 / Kotlin 2.1.0 — pinned in the plan against the
  compatibility table; if it forces a CMP/Kotlin bump, the plan advances the set together.
- **iOS compile with nav-compose** — expected fine (multiplatform), but the plan's iOS compile
  guard is the check.
- **Nav-arg types** (Float rating, Int count) — encode/parse correctly; a malformed arg must not
  crash the detail screen (default/guard).

## Deferred
P3a map polish; full-screen actions (share / open-in-maps / directions); filters/search;
recent-rides; rotation/resource retention; a11y; iOS map.
