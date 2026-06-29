# Current Location Button Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an OsmAnd-style GPS button to the map that, on tap, navigates to the user's location and shows a "you are here" dot that fades blue→grey over 30s — without requesting geolocation until the button is tapped.

**Architecture:** A custom Leaflet `L.Control` is added bottom-right above the existing zoom control. On tap it calls `map.locate(...)` (the only geolocation request in the app); `locationfound` drops a single `divIcon` dot + accuracy circle held in module-level vars and re-used on repeat taps; `locationerror` reverts the button. The dot's blue→grey fade is a pure CSS transition triggered one frame after insertion.

**Tech Stack:** Leaflet 1.9.4 (already loaded), Font Awesome 6 (already loaded), vanilla JS in `hitch/static/map.js`, CSS in `hitch/static/style.css`.

## Global Constraints

- **No geolocation on load.** `navigator.geolocation` / `map.locate()` may only be invoked as a direct result of a button tap. Verify no prompt appears on page load.
- **Not wired to add a point.** The button only navigates/displays; it must not touch the ride-submission / add-point path.
- **Match existing patterns.** Follow the geocoder/route-button setup style (a `setup…()` function called from the IIFE in `map.js`), and the existing `.leaflet-bar` / `.geocoder-route-btn` CSS conventions (use `!important` where Leaflet's `.leaflet-touch .leaflet-bar a` rules would otherwise win).
- **Icon:** Font Awesome 6 `fa-solid fa-location-crosshairs` (idle/active), `fa-solid fa-spinner fa-spin` (locating).
- **Colors:** dot starts blue `#1e88e5`, fades to grey `#9e9e9e` over **30s**.
- **No JS test harness exists** in this repo. Each task's verification is a manual browser check; perform it and confirm the stated observation before committing.

---

### Task 1: Add the locate control button (idle, placement, CSS)

Render a styled GPS button bottom-right above the zoom control. No behavior yet beyond a click handler stub that does nothing. Confirms placement/styling and that nothing requests geolocation on load.

**Files:**
- Modify: `hitch/static/map.js` — add `setupLocateControl()` and call it from the init IIFE (around `hitch/static/map.js:261-262`, after `setupGeocoder()`).
- Modify: `hitch/static/style.css` — add `.locate-control` button styling (append near the existing zoom rules around `hitch/static/style.css:450-454`).

**Interfaces:**
- Consumes: the module-level `map` (set by `createMap()` in `hitch/static/map.js:27`).
- Produces:
  - `function setupLocateControl()` — creates the control and adds it to `map`; safe to call once after `setupGeocoder()`.
  - Module-level state (declared near the other top-level `let`s around `hitch/static/map.js:24`), used by later tasks:
    - `let locateButtonEl = null;` — the `<a>` element of the control.
    - `let locationMarker = null;` — the `L.Marker` dot (created in Task 2).
    - `let locationAccuracyCircle = null;` — the `L.Circle` (created in Task 2).

- [ ] **Step 1: Declare module-level state**

Near the other top-level declarations (e.g. just after `hitch/static/map.js:24`, alongside `ridesIndex = null;`), add:

```javascript
// Current-location button state. The marker/circle are created lazily on the
// first successful locate and re-used on subsequent taps so taps never stack
// markers. Geolocation is only ever requested from the button's click handler.
let locateButtonEl = null;
let locationMarker = null;
let locationAccuracyCircle = null;
```

- [ ] **Step 2: Add `setupLocateControl()`**

Add this function next to `setupGeocoder` (e.g. after it ends at `hitch/static/map.js:353`):

```javascript
// OsmAnd-style "current location" button. Anchored bottom-right above the zoom
// control. Requirement: geolocation must NOT be requested on page load — the
// only call to map.locate()/navigator.geolocation happens in the tap handler
// (wired in Task 2). This task only renders the idle button.
function setupLocateControl() {
  const LocateControl = L.Control.extend({
    options: { position: "bottomright" },
    onAdd: function () {
      const container = L.DomUtil.create("div", "leaflet-bar locate-control");
      const btn = L.DomUtil.create("a", "locate-control-btn", container);
      btn.href = "#";
      btn.title = "Show my location";
      btn.setAttribute("role", "button");
      btn.setAttribute("aria-label", "Show my location");
      btn.innerHTML = '<i class="fa-solid fa-location-crosshairs"></i>';
      // Keep taps on the button from reaching the map (pan/zoom/add-point).
      L.DomEvent.disableClickPropagation(container);
      L.DomEvent.on(btn, "click", function (e) {
        L.DomEvent.preventDefault(e);
        // Behavior wired in Task 2.
      });
      locateButtonEl = btn;
      return container;
    },
  });
  new LocateControl().addTo(map);
}
```

- [ ] **Step 3: Call it from the init IIFE**

In the async IIFE, immediately after `setupGeocoder();` (`hitch/static/map.js:262`), add:

```javascript
  setupLocateControl();
```

- [ ] **Step 4: Add the button CSS**

Append to `hitch/static/style.css` (near the zoom rule at line ~452). The control sits in the same bottom-right stack as zoom; push it above zoom (zoom has `margin-bottom: 84px`). `!important` mirrors `.geocoder-route-btn` to beat Leaflet's `.leaflet-touch .leaflet-bar a`:

```css
/* OsmAnd-style current-location button, stacked above the zoom control */
.leaflet-bottom.leaflet-right .locate-control {
  margin-bottom: 134px !important; /* sits above zoom (84px) + zoom height */
  margin-right: 10px !important;
}

.locate-control-btn {
  display: flex !important;
  align-items: center;
  justify-content: center;
  width: 34px !important;
  height: 34px !important;
  background: white;
  color: #5f6368 !important;
  font-size: 18px;
  text-decoration: none;
  border-radius: 4px !important;
}

.locate-control-btn:hover {
  background: #f5f5f5;
  color: #1a73e8 !important;
}

/* Active = a location fix is currently shown on the map */
.locate-control-btn.locate-active {
  color: #1e88e5 !important;
}

/* Locating = waiting for a fix; the spinner icon replaces the crosshairs */
.locate-control-btn.locate-busy {
  color: #1e88e5 !important;
}
```

- [ ] **Step 5: Verify in browser**

Run the app (`flask run`) and open the map. Confirm:
- A white GPS (crosshairs) button appears bottom-right, above the zoom +/- control, not overlapping it or the attribution.
- No browser geolocation permission prompt appears on load.
- Clicking the button does nothing yet and does not add a point or pan the map.

In DevTools Console, run `navigator.permissions.query({name:'geolocation'}).then(p=>console.log(p.state))` — expected `prompt` (i.e. not yet requested) on a fresh profile.

- [ ] **Step 6: Commit**

```bash
git add hitch/static/map.js hitch/static/style.css
git commit -m "feat: add idle current-location button to map"
```

---

### Task 2: Wire tap → locate, show dot + accuracy circle, handle errors

Make the button actually locate the user: spinner while locating, drop/re-use a "you are here" dot + accuracy circle on success, active state while shown, graceful revert on error. Dot color is static here (Task 3 adds the fade).

**Files:**
- Modify: `hitch/static/map.js` — flesh out the click handler from Task 1 and add `requestLocation()`, `showLocation(e)`, `onLocationError(e)` helpers; register Leaflet `locationfound`/`locationerror` listeners inside `setupLocateControl()`.
- Modify: `hitch/static/style.css` — add `.user-location-dot` styling (the `divIcon` inner element) and the accuracy-circle is styled via Leaflet path options in JS.

**Interfaces:**
- Consumes (from Task 1): `map`, `locateButtonEl`, `locationMarker`, `locationAccuracyCircle`.
- Produces:
  - `function requestLocation()` — called by the tap handler; sets the busy state and calls `map.locate({ setView: true, maxZoom: 16, enableHighAccuracy: true, timeout: 10000 })`.
  - `function showLocation(e)` — `locationfound` handler; `e.latlng` + `e.accuracy` (metres). Creates or moves `locationMarker` (an `L.marker` using a `divIcon` whose inner `<div>` has class `user-location-dot`) and `locationAccuracyCircle` (an `L.circle`). Sets the button to active.
  - `function onLocationError(e)` — `locationerror` handler; reverts the button and `alert(...)`s a short message.
  - `function setLocateButtonState(state)` — `state` ∈ `"idle" | "busy" | "active"`; swaps icon + classes on `locateButtonEl`.

- [ ] **Step 1: Add the button-state helper**

Add above `setupLocateControl()` in `hitch/static/map.js`:

```javascript
// Single source of truth for the locate button's visual state.
//   idle   -> crosshairs, default colour
//   busy   -> spinner, while waiting for a fix
//   active -> crosshairs, blue, while a fix is shown on the map
function setLocateButtonState(state) {
  if (!locateButtonEl) return;
  locateButtonEl.classList.remove("locate-busy", "locate-active");
  if (state === "busy") {
    locateButtonEl.classList.add("locate-busy");
    locateButtonEl.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';
  } else {
    if (state === "active") locateButtonEl.classList.add("locate-active");
    locateButtonEl.innerHTML = '<i class="fa-solid fa-location-crosshairs"></i>';
  }
}
```

- [ ] **Step 2: Add `requestLocation`, `showLocation`, `onLocationError`**

Add below `setLocateButtonState`:

```javascript
// The ONLY place geolocation is requested. Called from the button tap handler,
// never on load. setView pans/zooms the map to the fix.
function requestLocation() {
  setLocateButtonState("busy");
  map.locate({
    setView: true,
    maxZoom: 16,
    enableHighAccuracy: true,
    timeout: 10000,
  });
}

// locationfound handler. Re-uses a single marker + accuracy circle so repeated
// taps never stack markers on the map.
function showLocation(e) {
  const radius = e.accuracy; // metres

  if (locationMarker) {
    locationMarker.setLatLng(e.latlng);
  } else {
    const icon = L.divIcon({
      className: "user-location-marker",
      html: '<div class="user-location-dot"></div>',
      iconSize: [18, 18],
      iconAnchor: [9, 9],
    });
    locationMarker = L.marker(e.latlng, {
      icon: icon,
      interactive: false,
      keyboard: false,
    }).addTo(map);
  }

  if (locationAccuracyCircle) {
    locationAccuracyCircle.setLatLng(e.latlng).setRadius(radius);
  } else {
    locationAccuracyCircle = L.circle(e.latlng, {
      radius: radius,
      interactive: false,
      color: "#1e88e5",
      weight: 1,
      fillColor: "#1e88e5",
      fillOpacity: 0.12,
    }).addTo(map);
  }

  setLocateButtonState("active");
}

// locationerror handler: permission denied, position unavailable, or timeout.
function onLocationError(e) {
  setLocateButtonState(locationMarker ? "active" : "idle");
  alert("Could not get your location: " + e.message);
}
```

- [ ] **Step 3: Register listeners and wire the tap handler**

In `setupLocateControl()`, replace the placeholder click handler body (`// Behavior wired in Task 2.`) with a call to `requestLocation()`:

```javascript
      L.DomEvent.on(btn, "click", function (e) {
        L.DomEvent.preventDefault(e);
        requestLocation();
      });
```

And, after `new LocateControl().addTo(map);` at the end of `setupLocateControl()`, register the map listeners once:

```javascript
  map.on("locationfound", showLocation);
  map.on("locationerror", onLocationError);
```

- [ ] **Step 4: Add the dot + marker CSS**

Append to `hitch/static/style.css`:

```css
/* "You are here" dot (inner element of the Leaflet divIcon). Task 3 animates
   its colour from blue to grey; this static colour is the starting point. */
.user-location-dot {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #1e88e5;
  border: 3px solid #fff;
  box-shadow: 0 0 4px rgba(0, 0, 0, 0.4);
  box-sizing: border-box;
}
```

- [ ] **Step 5: Verify in browser**

Reload the map (still no prompt on load). Then:
- Tap the button → permission prompt appears; the icon shows a spinner while waiting.
- Allow → map pans/zooms to your location; a blue dot with white ring + translucent blue accuracy circle appears; the button turns blue (active) with crosshairs.
- Tap again → map re-centers; exactly one dot/circle remains (no stacking).
- Reload, tap, and **deny** (or use DevTools Sensors → location "unavailable") → an alert shows the error and the button returns to idle (or stays active if a previous fix is shown); no dot added on first-time deny.

- [ ] **Step 6: Commit**

```bash
git add hitch/static/map.js hitch/static/style.css
git commit -m "feat: locate user and show position on map"
```

---

### Task 3: Blue→grey 30s freshness fade

Make the dot (and accuracy circle) start blue and transition to grey over 30s on every successful locate, signalling the fix is a one-time snapshot. Each tap resets to blue.

**Files:**
- Modify: `hitch/static/map.js` — in `showLocation`, restart the fade on each `locationfound` (re-trigger the CSS transition; reset the circle colour to blue and animate it to grey).
- Modify: `hitch/static/style.css` — add the CSS transition + `.stale` end-state for `.user-location-dot`.

**Interfaces:**
- Consumes: `locationMarker`, `locationAccuracyCircle`, `showLocation` (from Task 2).
- Produces: no new exported names; `showLocation` gains fade-restart logic, and a module-level `let locationFadeTimer = null;` for the accuracy-circle colour fade.

- [ ] **Step 1: Add the CSS transition + stale state**

Update the `.user-location-dot` rule and add a `.stale` modifier in `hitch/static/style.css`. The dot starts blue; adding `.stale` one frame later transitions `background` to grey over 30s:

```css
.user-location-dot {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #1e88e5;
  border: 3px solid #fff;
  box-shadow: 0 0 4px rgba(0, 0, 0, 0.4);
  box-sizing: border-box;
  /* Freshness fade: blue (fresh fix) -> grey (stale, not live-updated) over 30s */
  transition: background-color 30s linear;
}

.user-location-dot.stale {
  background: #9e9e9e;
}
```

- [ ] **Step 2: Restart the dot fade on each locate**

Add a module-level timer declaration next to the other locate state (near `hitch/static/map.js:24`):

```javascript
let locationFadeTimer = null;
```

In `showLocation`, after the marker is created/moved, reset and re-trigger the dot fade. Because the marker is re-used, grab its dot element and restart the CSS transition:

```javascript
  // Restart the blue->grey freshness fade on every fix. The dot element is
  // re-created implicitly only when the marker is new, so always re-query it
  // and toggle .stale off (blue) then on (animate to grey) across a frame.
  const dotEl = locationMarker.getElement()
    ? locationMarker.getElement().querySelector(".user-location-dot")
    : null;
  if (dotEl) {
    dotEl.classList.remove("stale");
    // Force a reflow so removing/re-adding .stale restarts the transition.
    void dotEl.offsetWidth;
    requestAnimationFrame(() => dotEl.classList.add("stale"));
  }
```

- [ ] **Step 3: Fade the accuracy circle too**

Leaflet path colours are SVG attributes (no CSS transition), so animate the circle colour in JS. In `showLocation`, after the circle is created/moved, reset it to blue and schedule a grey set after 30s:

```javascript
  // Match the dot: circle starts blue, becomes grey after the 30s fade window.
  locationAccuracyCircle.setStyle({ color: "#1e88e5", fillColor: "#1e88e5" });
  if (locationFadeTimer) clearTimeout(locationFadeTimer);
  locationFadeTimer = setTimeout(function () {
    if (locationAccuracyCircle) {
      locationAccuracyCircle.setStyle({ color: "#9e9e9e", fillColor: "#9e9e9e" });
    }
  }, 30000);
```

- [ ] **Step 4: Verify in browser**

Reload, tap, allow. Confirm:
- The dot is blue immediately after the fix, then visibly transitions toward grey over ~30s.
- After ~30s the dot is grey and the accuracy circle has turned grey.
- Tapping again resets the dot to blue and restarts the fade (circle returns to blue then fades again).

To speed verification you may temporarily change `30s`/`30000` to `3s`/`3000`, but **restore them to 30 before committing**.

- [ ] **Step 5: Commit**

```bash
git add hitch/static/map.js hitch/static/style.css
git commit -m "feat: fade location dot blue to grey over 30s to show staleness"
```

---

## Self-Review Notes

- **Spec coverage:** Placement/appearance → Task 1. One-time locate + dot + accuracy circle + error handling + no-prompt-on-load → Tasks 1–2. Blue→grey 30s fade → Task 3. Not-wired-to-add-point → enforced via `disableClickPropagation` (Task 1) and never touching ride flow. Out-of-scope items (tracking, heading, persistence) are not implemented.
- **Type/name consistency:** `setupLocateControl`, `setLocateButtonState`, `requestLocation`, `showLocation`, `onLocationError`, and the vars `locateButtonEl` / `locationMarker` / `locationAccuracyCircle` / `locationFadeTimer` are used consistently across tasks.
- **Testing reality:** No JS test runner exists in this repo; verification is manual browser checks (stated per task), which is appropriate for browser-geolocation UI.
