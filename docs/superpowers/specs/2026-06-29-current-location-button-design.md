# Current Location Button — Design

**Date:** 2026-06-29
**Status:** Approved

## Goal

Add an OsmAnd-style GPS button to the map. On tap it requests the user's
location, pans/zooms the map to it, and shows the user on the map with a
"you are here" marker. The button is **not** wired to add a point — it only
navigates and displays the current location.

**Privacy requirement:** the app must not request geolocation on load. The
browser permission prompt may only appear as a result of the user tapping the
button.

## Placement & Appearance

- Implemented as a custom Leaflet control (`L.Control` subclass) added to the
  map, anchored **bottom-right, directly above the existing zoom control**.
- Styled as a square white button matching the existing `.leaflet-bar`
  controls (zoom, route button), using the Font Awesome 6
  `fa-location-crosshairs` icon to match the OsmAnd GPS look. FA6 is already
  loaded in `map.html`.
- CSS lives in `style.css` alongside the existing zoom/route-button rules and
  respects the same bottom-stacking (`margin-bottom`) so it sits above the
  bottom action pane and attribution.

## Behavior (one-time locate)

1. **Tap → locating state.** The button swaps its icon to a spinner
   (`fa-spinner fa-spin`) and calls
   `map.locate({ setView: true, maxZoom: 16, enableHighAccuracy: true })`.
   This is the first and only place geolocation is requested, so the browser
   permission prompt appears only on tap.

2. **`locationfound` → show the user.** Drop/update:
   - a single **"you are here" dot marker** (a Leaflet `divIcon`), and
   - a translucent **accuracy circle** sized to `e.accuracy`.

   Both are stored in module-level vars so repeat taps reuse/replace them
   rather than stacking. The button returns from the spinner to an **active**
   state while the marker is on the map.

3. **`locationerror` → graceful failure.** On permission denied, position
   unavailable, or timeout, the button reverts to idle and a brief
   non-blocking message is shown (reuse the app's existing toast/notice
   pattern if one exists; otherwise a small inline message). No marker added.

## Freshness Fade (blue → grey over 30s)

To communicate that the displayed location is a one-time snapshot and not
continuously updated:

- When the location is first shown (each `locationfound`), the dot starts
  **blue** (OsmAnd-style, e.g. `#1e88e5`).
- Over a **30-second** period it transitions to **grey** (e.g. `#9e9e9e`),
  signalling the fix is now stale.
- **Implementation:** the marker is an `L.divIcon` whose inner element uses a
  CSS `transition` on its color/background from blue to grey over 30s. Adding
  a "stale" class (or toggling the start/end state) one frame after insertion
  triggers the transition. Each new tap recreates/resets the dot so it starts
  blue again.
- The accuracy circle may follow the same fade for consistency, but the dot is
  the primary indicator.

## Isolation

- All logic lives in a small self-contained block in `map.js` — a
  `setupLocateControl()` function called from map init, mirroring how the
  geocoder and route button are set up. Module-level vars hold the current
  location marker and accuracy circle.
- A focused CSS block in `style.css` covers the button and the dot/fade.
- No changes to data flow, ride submission, filtering, or the add-point path.

## Out of Scope (YAGNI)

- Continuous tracking / `watchPosition` (one-time locate only).
- Heading/compass direction arrow.
- Persisting the location across reloads.
- Any wiring to the add-point / ride-submission flow.

## Testing

- This is a frontend-only, browser-geolocation feature; automated coverage is
  limited. Verify manually:
  - No geolocation prompt on page load.
  - Tapping the button triggers the prompt; on allow, map centers and the dot +
    accuracy circle appear; the dot starts blue and fades to grey over ~30s.
  - Tapping again re-centers and resets the dot to blue without stacking
    markers.
  - On deny, the button reverts to idle with a brief message and no marker.
