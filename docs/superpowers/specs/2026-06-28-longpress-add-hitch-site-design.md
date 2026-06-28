# Long-press / right-click to add a hitch site — Design

**Date:** 2026-06-28
**Status:** Approved (design)
**Scope:** Frontend only — `hitch/static/map.js`. No backend, template, or service-worker changes.

## Goal

On the map (primarily the mobile PWA saved to the homescreen, but also desktop), let the
user drop a pin at an arbitrary point and open the existing ride-submission form pre-filled
with that point as the pickup location, so they can add a hitch site to the database.

- **Touch:** long-press the map.
- **Desktop:** right-click (contextmenu) the map.

## Context / existing infrastructure being reused

The map already has a complete draggable-marker location-selection mode, used today when a
user picks the pickup/destination location from the ride form:

- Hash route `#select-pickup/<lat,lon,zoom>` (and `select-destination`) is handled in the
  hashchange/navigate logic at `hitch/static/map.js:1410`, which calls `setupLocationSelection`.
- `setupLocationSelection(selectionType, coordsArg)` (`map.js` ~2070) drops a **draggable**
  red marker, lets a map click reposition it, and renders a fixed white panel with
  **Confirm Location** / **Cancel** buttons.
- `confirmLocationSelection()` (`map.js:2119`) reads the marker latlng, writes
  `pickup_lat`/`pickup_lon` (or destination) into `sessionStorage.rideFormData`, and
  navigates to `/ride` (or `/ride?edit=<d_tag>` when editing).
- `cancelLocationSelection()` (`map.js:2142`) cleans up and navigates back to `/ride`.
- The ride form (`hitch/templates/ride_form.html`, `restoreFormData()` ~397) reads
  `sessionStorage.rideFormData` on load and pre-fills the pickup location from it.

The ride form already supports **anonymous** submission, so no authentication gating is needed.

The service worker (`hitch/static/sw.js`) is **network-first** for non-image resources
(scripts included), so the updated `map.js` propagates to the installed PWA on the next
online load. **No cache-version bump is required.**

## Approach

Chosen approach (A): trigger the existing selection-mode machinery from a gesture instead of
from a hash arriving from the form. This keeps a single, proven selection/confirm code path.

## Design

### 1. Gesture detection (new listeners attached where the map is initialized)

**Touch long-press:**
- On `touchstart`: if exactly one touch, record the touch client point and start a timer
  (`LONG_PRESS_MS = 500`).
- Cancel the timer on:
  - `touchmove` where the touch moves more than a small threshold
    (`MOVE_CANCEL_PX = 10`) from the start point — so map panning never triggers it;
  - `touchend`/`touchcancel` before the timer fires;
  - a second touch starting (pinch-zoom).
- When the timer fires: convert the recorded point to a Leaflet container point and latlng
  (`map.containerPointToLatLng`), call `startAddSpotFromGesture(latlng, containerPoint)`, and
  suppress the default callout/selection (`preventDefault` on the originating event where
  possible).

**Desktop right-click:**
- `map.on('contextmenu', (e) => { e.originalEvent.preventDefault();
  startAddSpotFromGesture(e.latlng, e.containerPoint); })`.
  Leaflet provides `e.latlng` and `e.containerPoint`; prevent the browser context menu.

The gesture must not interfere with existing marker clicks (`marker.on("click", …)`),
filter-pane interactions, or panning/zoom. Long-press on top of an existing marker is
acceptable — the user can drag the resulting pin or cancel.

### 2. Enter selection mode at the pressed point (with snap-to-existing-spot)

New function `startAddSpotFromGesture(latlng, containerPoint)`:
1. `sessionStorage.removeItem('rideFormData')` — start a **fresh** ride: no edit mode, no
   stale fields from a previous session.
2. **Snap check:** call `findNearbySpotMarker(containerPoint)` (see §2a). If it returns a
   marker, use that marker's exact `getLatLng()` as the seed location and flag the add as an
   *existing-spot* add; otherwise use the raw `latlng` as a *new-spot* add.
3. Enter the selection mode seeded at the chosen location (see §3):
   effectively `setupLocationSelection('select-pickup', null,
   { initialLatLng: seedLatLng, isNewSpot: true, existingSpot: <bool> })`.

No hash round-trip is required; the function is called directly.

Snapping to the marker's **exact** lat/lon is important: spot IDs are derived from lat/lon at
5 decimals (`generate_spot_id` in `show.py`, mirrored at `map.js:96`), so a ride seeded at the
exact coords merges into the same spot rather than creating a near-duplicate anchor.

### 2a. `findNearbySpotMarker(containerPoint, thresholdPx = 22)`

New helper that returns the nearest existing spot marker to a screen point, or `null`:
- Iterate the global `allMarkers` array (populated in `loadMarkers`).
- **Skip clustered markers:** below `disableClusteringAtZoom` (7) markers are hidden inside
  clusters. Skip any marker whose visible parent is a cluster
  (`markerCluster.getVisibleParent(marker) !== marker`) so we only snap to a pin the user can
  actually see. This requires `markerCluster` to be reachable from the helper — promote the
  currently-local `markerCluster` (in `loadMarkers`) to a module-scope variable.
- For each remaining marker, compute the pixel distance between
  `map.latLngToContainerPoint(marker.getLatLng())` and `containerPoint`.
- Return the closest marker whose distance `<= thresholdPx`, else `null`.

The desktop `contextmenu` handler supplies `containerPoint` from
`map.latLngToContainerPoint(e.latlng)` (or `e.containerPoint` if available); the touch handler
computes it from the recorded touch point.

### 3. Refactor `setupLocationSelection`

Extend the signature to accept optional behavior without changing existing callers:

- New optional `opts = { initialLatLng, isNewSpot }`.
- When `opts.initialLatLng` is provided, place the draggable marker there (instead of map
  center / parsed coords). Existing form-driven callers pass no opts and keep current behavior.
- When `opts.isNewSpot` is true, relabel the confirm panel:
  - If `opts.existingSpot` (snapped to an existing pin):
    - Heading: **"Add a ride to this spot"**
    - Instruction: **"This matches an existing hitch spot. Confirm to add your ride here."**
    - Confirm button text: **"Add ride"**.
  - Otherwise (fresh point):
    - Heading: **"Add a hitch spot here?"**
    - Instruction: **"Drag the pin to fine-tune, then confirm."**
    - Confirm button text: **"Add spot"**.
  - When neither flag is set, keep the existing "Select Pickup/Destination Location" copy.
- Persist the `isNewSpot` flag alongside the existing `locationSelectionType` module state so
  confirm/cancel can branch on it. (`existingSpot` only affects panel copy, not confirm/cancel
  behavior — a snapped pin is still draggable, and dragging away from the spot simply creates a
  new one.)

### 4. Confirm / Cancel

- **Confirm** (`confirmLocationSelection`): unchanged logic — write `pickup_lat`/`pickup_lon`
  into `rideFormData` and navigate to `/ride`. Because `rideFormData` was cleared in §2 and
  there is no `edit_d_tag`, the form opens fresh with only the pickup pre-filled.
- **Cancel** (`cancelLocationSelection`): branch on the new-spot flag.
  - New-spot mode: clean up the marker/panel and **return to the map** (remove the marker,
    remove the UI, clear any selection hash via `history.replaceState`). Do **not** navigate
    to `/ride`.
  - Form-driven mode: unchanged (navigate back to `/ride`, preserving edit mode).

### 5. Module state / cleanup

- Reuse existing `locationSelectionMarker` / `locationSelectionType` module variables; add a
  `locationSelectionIsNewSpot` (or fold into an options object) for the branch.
- `cleanupLocationSelection` continues to remove the marker, remove the panel, and detach the
  temporary `map.on('click')` handler; ensure the new-spot path calls it.

## Out of scope (YAGNI)

- No new lightweight modal or new "add spot" page — reuse the existing `/ride` form.
- No reverse-geocoding / address lookup of the pressed point.
- No new backend endpoint or model changes (submission goes through the existing form/POST).
- No service-worker changes.

## Testing / verification (manual)

There is no JS test harness in the repo (tests are pytest/Python), so verification is manual
in the browser and the installed PWA:

1. **Desktop right-click** on an empty map area → draggable pin + "Add a hitch spot here?"
   panel appears at the clicked point; browser context menu does not appear.
2. **Mobile long-press** (touch device / emulation) on the map → same pin + panel at the
   pressed point.
3. **Drag** the pin → position updates; tapping the map also repositions it.
4. **Confirm ("Add spot")** → navigates to `/ride` with the pickup location pre-filled to the
   pin location and the rest of the form empty.
5. **Cancel** → returns to the map (pin and panel removed), no navigation to `/ride`.
6. **Snap to existing pin:** long-press/right-click directly on (or within ~22px of) an
   existing spot marker → the pin seeds at that marker's exact location and the panel reads
   "Add a ride to this spot". Confirm → `/ride` with pickup at the spot's coords, so the ride
   merges into that spot.
7. **No false snap:** pressing in empty space well away from any marker → "Add a hitch spot
   here?" (no snap).
8. **No snap to clustered pins:** at a low zoom where spots are clustered, pressing on a
   cluster does **not** snap to a hidden marker.
9. **Panning** (touch drag) does **not** trigger the long-press.
10. **Pinch-zoom** (two fingers) does **not** trigger the long-press.
11. The existing form-driven "select pickup/destination on map" flow still works unchanged.
12. In the installed PWA, after an online load, the new gesture is available (network-first SW).
