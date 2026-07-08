# In-Ride Hitching Tracker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a live "in-ride" journey tracker to the map that logs a real ride with near-zero typing — auto-capturing pickup, wait time (pause-aware), departure/arrival times, and destination from big-button taps + GPS.

**Architecture:** A self-contained front-end state machine (`hitch/static/inride.js`) layered on the existing Leaflet map, persisted in `localStorage` (survives reloads / long waits). It reuses existing building blocks (`locationMarker`, `setupLocationSelection`, `findNearbySpotMarker`, `setMapMode`, `toggleHeatmap`, the locate control) and submits the finished ride through the existing `/ride` backend. To keep the post-ride "What's next?" flow on the map, `/ride` gains a JSON response branch (used only by this feature); everything else about `/ride` is unchanged.

**Tech Stack:** Vanilla JS + Leaflet 1.x (front end), Flask + SQLAlchemy + Nostr publish (back end, unchanged logic), plain CSS. No JS test framework exists in the repo (Python/pytest only), so front-end tasks verify manually via the running app + cloudflared tunnel; the one backend change gets a pytest.

## Global Constraints

- **Copy (verbatim):** choose-action title "This spot", body "Track a ride from here now — or log a ride you already got."; buttons **Start Hitching** (green `#1a9850`), **Log a past ride** (blue-outline). Soft-login title "Track your rides?", buttons **Log in** / **Continue anonymously**. Waiting buttons **Give Up** (red `#d73027`) / **Got a Ride!** (green). Pause pill **Pause** / **Resume**. Ride-details sheet title "How was the spot?", CTA **Ride On!**. In-ride button **Finish Ride** (orange `#ff6b35`). Post-ride title "What's next?", buttons **Next Ride** / **End Hitch**. Set-waiting-spot title "Where are you waiting?".
- **Colors:** blue `#1a73e8`, green `#1a9850`, red `#d73027`, orange `#ff6b35`. Match existing `style.css` tokens.
- **No login gate** to *start*; anonymous is allowed end-to-end (soft prompt only). Ride submits anonymously when logged out, exactly like the current add-spot flow.
- **Discrete GPS only** — no continuous/background tracking. GPS fixes happen only at Start Hitching (pickup) and Finish Ride (destination); a "fix" = up to **3 attempts** on timeout/position-error before failing (permission *denial* is terminal → manual pin).
- **The locate control never feeds the flow** — it stays "show my location". During a journey it + the Spots/Heatmap/Countries switcher become one **cover-flow stack**, positioned **above the zoom control** so nothing is ever covered.
- **Wait time excludes paused time** (active-wait accumulator).
- **Requirement comments:** per `CLAUDE.md`, add a comment above non-obvious logic explaining the "why".
- **Ruff:** any Python must pass `ruff check` / `ruff format` (line length 130).

---

## File Structure

- **Create** `hitch/static/inride.js` — the whole feature: `journeyStore` (localStorage + accumulator), `journeyFlow` (transitions), `journeyUI` (docked bars, chip+timer, dialogs, cover-flow), and the GPS-with-retry helper. Loaded after `map.js`.
- **Modify** `hitch/static/map.js` — expose the hooks `inride` needs, and let `inride` intercept the long-press / bubble-tap entry points and hide the stock map-mode + locate controls while a journey is active.
- **Modify** `hitch/static/style.css` — journey UI styles (docked bar, status chip, pause pill, ride-details sheet, cover-flow tiles).
- **Modify** `hitch/templates/map.html` — expose `is_logged_in` to JS; `<script>` include `inride.js`.
- **Modify** `hitch/blueprints/main.py` — add a JSON-response branch to the existing `/ride` POST for programmatic (in-ride) submission.
- **Create** `tests/test_inride_submit.py` — pytest for the JSON branch.

Interface glossary (names used across tasks):
- `window.IS_LOGGED_IN: boolean`
- `journeyStore.get(): Journey|null`, `.set(j)`, `.clear()`, `.currentWaitMs(j): number`
- `Journey = { state:'waiting'|'paused'|'in-ride', pickup:{lat,lon}, waitAccumMs:number, waitSegmentStartMs:number|null, gotRideMs:number|null, finalWaitMs:number|null, details:object|null, legIndex:number }`
- `getFixWithRetry(opts): Promise<{lat,lon}>` — resolves a GPS fix (≤3 tries) or rejects `{code:'denied'|'unavailable'}`
- `journeyFlow.start(latlng)`, `.pause()`, `.resume()`, `.giveUp()`, `.gotRide(details)`, `.finish()`, `.nextRide(latlng)`, `.end()`
- `journeyUI.render(journey|null)` — single entry point that (re)draws all journey chrome for the current state
- map.js exposes on `window`: `map`, `getLocationMarker()`, `setMapMode`, `toggleHeatmap`, `requestLocationRaw()`, `startAddSpotFromGesture`, `setupLocationSelection`, `findNearbySpotMarker`, and calls `window.inrideOnEntryGesture(latlng, containerPoint)` when a long-press / bubble-tap occurs.
- Backend: `POST /ride` with header `X-Requested-With: inride` (or form field `ajax=1`) returns `{"ok":true,"d_tag":"..."}` / `{"ok":false,"error":"..."}` instead of redirecting.

---

## Task 1: Scaffold `inride.js`, expose login flag, journeyStore + accumulator

**Files:**
- Modify: `hitch/templates/map.html` (expose `is_logged_in`; include `inride.js`)
- Create: `hitch/static/inride.js`

**Interfaces:**
- Produces: `window.IS_LOGGED_IN`; `journeyStore.get/set/clear/currentWaitMs`; the `Journey` shape above.

- [ ] **Step 1: Expose the login flag to JS** in `hitch/templates/map.html`, immediately before the existing `<script src="{{ asset_url('/static/map.js') }}"></script>` line:

```html
<!-- Expose auth state to the in-ride tracker (it decides whether to show the soft login prompt). -->
<script>window.IS_LOGGED_IN = {{ 'true' if is_logged_in else 'false' }};</script>
<script src="{{ asset_url('/static/map.js') }}"></script>
<script src="{{ asset_url('/static/inride.js') }}"></script>
```

- [ ] **Step 2: Create `hitch/static/inride.js`** with the store (single source of truth) and the pause-aware accumulator:

```js
// In-ride hitching tracker. A localStorage-backed state machine layered on the
// map. State + timestamps survive reloads so timing keeps running across a long
// wait or an app restart. See docs/superpowers/specs/2026-07-02-in-ride-hitching-tracker-design.md
(function () {
  "use strict";

  const KEY = "inride.journey";
  const PENDING_KEY = "inride.pendingStart"; // only across the login redirect

  const journeyStore = {
    get() {
      try { return JSON.parse(localStorage.getItem(KEY)); } catch (e) { return null; }
    },
    set(j) { localStorage.setItem(KEY, JSON.stringify(j)); return j; },
    clear() { localStorage.removeItem(KEY); },

    // Active wait in ms: banked segments + the running segment (0 while paused).
    // Authoritative value for the timer/label so reloads AND pauses stay exact.
    currentWaitMs(j, nowMs) {
      if (!j) return 0;
      const running = j.waitSegmentStartMs ? nowMs - j.waitSegmentStartMs : 0;
      return (j.waitAccumMs || 0) + Math.max(0, running);
    },
  };

  window.inride = { journeyStore }; // more attached in later tasks
})();
```

- [ ] **Step 3: Manual verification** — start the app and tunnel (see `CLAUDE.md`), open the map, and in the browser console:

Run:
```js
IS_LOGGED_IN                       // → true or false
inride.journeyStore.set({state:'waiting', waitAccumMs:0, waitSegmentStartMs:Date.now(), pickup:{lat:1,lon:2}, gotRideMs:null, finalWaitMs:null, details:null, legIndex:0});
inride.journeyStore.currentWaitMs(inride.journeyStore.get(), Date.now())  // → ~0 and rising
inride.journeyStore.clear(); inride.journeyStore.get()   // → null
```
Expected: values as annotated; no console errors; `/static/inride.js` returns 200 in the Network tab.

- [ ] **Step 4: Commit**

```bash
git add hitch/templates/map.html hitch/static/inride.js
git commit -m "feat(inride): scaffold module, expose login flag, journey store + wait accumulator"
```

---

## Task 2: Backend — JSON response branch on `POST /ride` (+ pytest)

**Why:** The finished ride must submit while the user stays on the map (for the "What's next?" prompt). The current handler ends in `redirect('/#success')`; add a branch that returns JSON when called by the tracker, reusing all publish logic.

**Files:**
- Modify: `hitch/blueprints/main.py` (the `POST` branch of `ride_form`, near its final `redirect(...)`)
- Test: `tests/test_inride_submit.py`

**Interfaces:**
- Produces: `POST /ride` with header `X-Requested-With: inride` → `200 {"ok":true,"d_tag":<str>}` on success, `400 {"ok":false,"error":<str>}` on validation failure — never a redirect.

- [ ] **Step 1: Read the current POST tail** to find the success redirect and the `d`/`d_tag` variable name and the exception handling:

Run: `grep -n "redirect(\|#success\|#failed\|d_tag\|except\|return " hitch/blueprints/main.py | sed -n '1,40p'`
Expected: locate the final `return redirect("/#success")` (success) and the failure path.

- [ ] **Step 2: Write the failing test** `tests/test_inride_submit.py` (follow the existing `tests/test_app.py` fixture style — reuse its app/client fixture; if it defines `client` in `conftest.py`, import that):

```python
# In-ride submissions must get JSON back (not a redirect) so the map UI can stay put.
def test_inride_submit_returns_json_ok(client, monkeypatch):
    # Stub the Nostr publish so the test doesn't hit the network; return a known d_tag.
    import hitch.blueprints.main as main
    monkeypatch.setattr(main, "publish_ride_to_nostr", lambda *a, **k: "dtag123", raising=False)
    resp = client.post(
        "/ride",
        data={
            "rate": "4", "wait": "12", "signal": "thumb", "comment": "",
            "pickup_lat": "48.2", "pickup_lon": "16.37",
            "destination_lat": "48.5", "destination_lon": "16.9",
            "datetime_ride": "2026-07-02T14:00", "arrival_datetime": "2026-07-02T14:41",
        },
        headers={"X-Requested-With": "inride"},
    )
    assert resp.status_code == 200
    assert resp.is_json
    assert resp.get_json()["ok"] is True
```

(Adjust the monkeypatch target to the actual publish function name/import found in Step 1.)

- [ ] **Step 3: Run the test to verify it fails**

Run: `python -m pytest tests/test_inride_submit.py -v`
Expected: FAIL (currently returns a 302 redirect, not JSON).

- [ ] **Step 4: Implement the JSON branch.** In `ride_form`'s POST path, replace the success `return redirect("/#success")` and wrap the validation body so both success and failure honor the header. Minimal shape:

```python
# In-ride tracker submits via fetch and must stay on the map, so answer JSON
# instead of the usual redirect. Detected by the X-Requested-With header.
wants_json = request.headers.get("X-Requested-With") == "inride"
# ... existing publish logic produces the new event's d tag (e.g. `d_tag`) ...
if wants_json:
    return jsonify({"ok": True, "d_tag": d_tag}), 200
return redirect("/#success")
```

And in the failure/except path:

```python
if request.headers.get("X-Requested-With") == "inride":
    return jsonify({"ok": False, "error": str(err)}), 400
# ... existing non-JSON failure handling (redirect to /#failed) ...
```

Ensure `jsonify` is imported (`from flask import ..., jsonify`).

- [ ] **Step 5: Run the test to verify it passes**

Run: `python -m pytest tests/test_inride_submit.py -v`
Expected: PASS.

- [ ] **Step 6: Regression + lint**

Run: `python -m pytest tests/ -q && ruff check hitch/blueprints/main.py tests/test_inride_submit.py`
Expected: all pass, no lint errors.

- [ ] **Step 7: Commit**

```bash
git add hitch/blueprints/main.py tests/test_inride_submit.py
git commit -m "feat(ride): JSON response branch on POST /ride for in-ride submissions"
```

---

## Task 3: map.js hooks + choose-action dialog + "Log a past ride"

**Files:**
- Modify: `hitch/static/map.js` (expose hooks; route long-press/bubble-tap through `inride`)
- Modify: `hitch/static/inride.js` (choose-action dialog + `journeyUI` dialog helpers)
- Modify: `hitch/static/style.css` (dialog/scrim styles — reuse `.location-selection-ui` look)

**Interfaces:**
- Consumes: `startAddSpotFromGesture`, `findNearbySpotMarker`, `locationMarker`.
- Produces: `window.inrideOnEntryGesture(latlng, containerPoint)`; `journeyUI.dialog({title, body, actions})` returning a promise/close handle; the choose-action dialog.

- [ ] **Step 1: Expose hooks in `map.js`.** After the map + controls are set up, add:

```js
// Expose the pieces the in-ride tracker composes with (it loads after map.js).
window.map = map;
window.getLocationMarker = () => locationMarker;
window.setMapMode = setMapMode;
window.toggleHeatmap = toggleHeatmap;
window.startAddSpotFromGesture = startAddSpotFromGesture;
window.setupLocationSelection = setupLocationSelection;
window.findNearbySpotMarker = findNearbySpotMarker;
```

- [ ] **Step 2: Route the long-press / right-click / bubble-tap through inride.** In `setupAddSpotGesture`, at the very start of the `contextmenu` handler and the touch long-press timer callback, delegate to inride first:

```js
// The in-ride tracker owns the "what do you want to do here?" decision now.
// If it handles the gesture (shows its choose-action dialog), stop here.
if (window.inrideOnEntryGesture && window.inrideOnEntryGesture(latlng, containerPoint)) return;
```

Also make the location bubble tappable — where `locationMarker` is created in `showLocation`, set `interactive: true, keyboard: false` and add:

```js
locationMarker.on("click", function () {
  const p = map.latLngToContainerPoint(locationMarker.getLatLng());
  if (window.inrideOnEntryGesture) window.inrideOnEntryGesture(locationMarker.getLatLng(), p);
});
```

(Requirement comment: the bubble is an entry point to the choose-action dialog; it must not itself set pickup/destination.)

- [ ] **Step 3: Implement `inrideOnEntryGesture` + choose-action dialog in `inride.js`.** Append to the module a `journeyUI.dialog()` (a scrim + bottom card, tap-scrim-to-cancel, buttons) and:

```js
// Entry point from map gestures. Returns true if we handled it (a journey is
// active → ignore; else show choose-action). Returning false lets map.js fall
// back to its old add-spot behavior (defensive; normally we always handle).
window.inrideOnEntryGesture = function (latlng, containerPoint) {
  if (journeyStore.get()) return true; // one journey at a time; ignore new gestures
  journeyUI.dialog({
    title: "This spot",
    body: "Track a ride from here now — or log a ride you already got.",
    actions: [
      { label: "Start Hitching", cls: "inr-go", onClick: () => journeyFlow.startFromChoose(latlng) },
      { label: "Log a past ride", cls: "inr-ghost",
        onClick: () => window.startAddSpotFromGesture(latlng, containerPoint) },
    ],
  });
  return true;
};
```

`journeyFlow.startFromChoose` is stubbed here to `console.log` (implemented in Task 4). `journeyUI.dialog` closes on scrim tap and on any action click.

- [ ] **Step 4: Add dialog CSS** to `style.css` mirroring `.location-selection-ui` (scrim `rgba(0,0,0,.28)`, white rounded card bottom-center `z-index:2002`, `.inr-go` green, `.inr-ghost` white/blue-outline). Requirement comment noting it matches the existing selection card.

- [ ] **Step 5: Manual verification** (app + tunnel): long-press the map → the "This spot" dialog appears with **Start Hitching** / **Log a past ride**. Tap **Log a past ride** → the existing add-spot confirm card appears (unchanged flow). Long-press again → **Start Hitching** logs to console. Tap outside the dialog → it cancels. Tap GPS, then tap the blue bubble → same dialog appears.

- [ ] **Step 6: Commit**

```bash
git add hitch/static/map.js hitch/static/inride.js hitch/static/style.css
git commit -m "feat(inride): choose-action dialog + entry-point hooks; Log a past ride reuses add-spot"
```

---

## Task 4: GPS-with-retry helper, soft login prompt, Start Hitching → waiting

**Files:**
- Modify: `hitch/static/inride.js` (`getFixWithRetry`, soft-login, `journeyFlow.start`)

**Interfaces:**
- Consumes: `journeyStore`, `IS_LOGGED_IN`, `setupLocationSelection` (manual-pin fallback).
- Produces: `getFixWithRetry(opts)`, `journeyFlow.start(latlng)`, `journeyFlow.startFromChoose(latlng)`.

- [ ] **Step 1: Implement `getFixWithRetry`** (≤3 attempts; denial is terminal):

```js
// A GPS "fix" = up to 3 attempts. Timeout / position-unavailable → retry;
// PERMISSION_DENIED (code 1) is terminal and rejects immediately so the caller
// can fall back to a manual pin without pointlessly retrying.
function getFixWithRetry({ tries = 3, timeout = 10000 } = {}) {
  return new Promise((resolve, reject) => {
    let n = 0;
    const attempt = () => {
      n++;
      navigator.geolocation.getCurrentPosition(
        (pos) => resolve({ lat: pos.coords.latitude, lon: pos.coords.longitude }),
        (err) => {
          if (err.code === 1) return reject({ code: "denied" });
          if (n < tries) return attempt();
          reject({ code: "unavailable" });
        },
        { enableHighAccuracy: true, timeout, maximumAge: 0 }
      );
    };
    attempt();
  });
}
```

- [ ] **Step 2: Implement the soft login prompt + start.** `startFromChoose` gates on auth; `start` seeds the journey:

```js
journeyFlow.startFromChoose = function (latlng) {
  if (window.IS_LOGGED_IN) return journeyFlow.start(latlng);
  journeyUI.dialog({
    title: "Track your rides?",
    body: "Log in to keep your ride history, or just continue anonymously.",
    actions: [
      { label: "Log in", cls: "inr-primary", onClick: () => {
          localStorage.setItem(PENDING_KEY, JSON.stringify({ lat: latlng.lat, lon: latlng.lng }));
          window.location.href = "/login?next=/";
        } },
      { label: "Continue anonymously", cls: "inr-grey", onClick: () => journeyFlow.start(latlng) },
    ],
  });
};

// Seed the waiting journey. Pickup = the chosen latlng; wait timer starts now.
journeyFlow.start = function (latlng) {
  const j = journeyStore.set({
    state: "waiting", pickup: { lat: latlng.lat, lon: latlng.lng },
    waitAccumMs: 0, waitSegmentStartMs: Date.now(),
    gotRideMs: null, finalWaitMs: null, details: null, legIndex: 0,
  });
  journeyUI.render(j);
};
```

(`journeyUI.render` is a stub logging the state until Task 5.)

- [ ] **Step 3: Manual verification:** logged out → **Start Hitching** shows "Track your rides?"; **Continue anonymously** → console shows a `waiting` journey stored (check `inride.journeyStore.get()`); **Log in** → navigates to `/login`. Logged in → **Start Hitching** goes straight to `waiting`. In console, force a denied fix to confirm no retry: temporarily call `getFixWithRetry()` and deny permission → rejects `{code:'denied'}` immediately.

- [ ] **Step 4: Commit**

```bash
git add hitch/static/inride.js
git commit -m "feat(inride): GPS retry helper, soft login prompt, Start Hitching seeds waiting"
```

---

## Task 5: Waiting UI — docked bar, status chip, live timer; resume-safe render

**Files:**
- Modify: `hitch/static/inride.js` (`journeyUI.render` for `waiting`, timer)
- Modify: `hitch/static/style.css` (`.inr-dock`, `.inr-big`, `.inr-chip`, `.inr-pausepill`)

**Interfaces:**
- Consumes: `journeyStore.currentWaitMs`, `journeyFlow.giveUp/gotRide` (stubs until Tasks 7–8).
- Produces: `journeyUI.render(journey)` for `waiting`; `journeyUI.teardown()`; `fmtHMS(ms)`.

- [ ] **Step 1: Implement render + timer.** `render` builds (once) a docked bar with **Give Up** (red) / **Got a Ride!** (green) and a status chip `Waiting · HH:MM:SS` with a **Pause** pill; a 1s interval updates the chip from `currentWaitMs` (authoritative, so reload/pause exact). `teardown()` removes the DOM + clears the interval. Include `fmtHMS`.

```js
function fmtHMS(ms) {
  const s = Math.floor(ms / 1000), h = Math.floor(s / 3600),
        m = Math.floor((s % 3600) / 60), ss = s % 60;
  const p = (n) => String(n).padStart(2, "0");
  return `${p(h)}:${p(m)}:${p(ss)}`;
}
```

Docked bar and chip are `position:fixed`, `z-index` above the map but the controls (Task 12) sit above them. Requirement comment: chip value derives from stored timestamps, never a counter, so reloads stay exact.

- [ ] **Step 2: Style** the dock/chip/pill in `style.css` (big buttons `border-radius:14px`, `font-weight:800`; chip dark pill bottom-center; pause pill translucent on the chip). Match mockup metrics.

- [ ] **Step 3: Manual verification:** start a journey → the docked Give Up / Got a Ride bar + a live `Waiting · 00:00:xx` timer appear and tick. Reload the page → they reappear and the timer reflects real elapsed time (Task 11 wires auto-resume; for now call `inride.journeyUI.render(inride.journeyStore.get())` in console to confirm the render path).

- [ ] **Step 4: Commit**

```bash
git add hitch/static/inride.js hitch/static/style.css
git commit -m "feat(inride): waiting docked bar + live wait timer"
```

---

## Task 6: Pause / Resume

**Files:**
- Modify: `hitch/static/inride.js` (`journeyFlow.pause/resume`, paused render branch)

**Interfaces:**
- Consumes: `journeyStore`.
- Produces: `journeyFlow.pause()`, `journeyFlow.resume()`; `journeyUI.render` handles `paused`.

- [ ] **Step 1: Implement pause/resume** (bank the running segment on pause; restart on resume):

```js
journeyFlow.pause = function () {
  const j = journeyStore.get(); if (!j || j.state !== "waiting") return;
  // Bank the active segment and stop the clock so a break/overnight is excluded.
  j.waitAccumMs = journeyStore.currentWaitMs(j, Date.now());
  j.waitSegmentStartMs = null; j.state = "paused";
  journeyUI.render(journeyStore.set(j));
};
journeyFlow.resume = function () {
  const j = journeyStore.get(); if (!j || j.state !== "paused") return;
  j.waitSegmentStartMs = Date.now(); j.state = "waiting";
  journeyUI.render(journeyStore.set(j));
};
```

- [ ] **Step 2: Paused render branch** — same dock as waiting but **Got a Ride!** disabled/greyed (`.inr-big.inr-disabled`), the chip shows `Paused · waited MM:SS` (frozen), and the pill becomes **Resume** (in the chip). Give Up stays active. Add `.inr-disabled` style.

- [ ] **Step 3: Manual verification:** while waiting, tap **Pause** → timer freezes, Got a Ride! greys out, chip shows "Paused · waited …" with a **Resume** pill; wait 20s, tap **Resume** → timer continues from where it froze (paused seconds NOT counted). Reload while paused → resumes paused, frozen.

- [ ] **Step 4: Commit**

```bash
git add hitch/static/inride.js hitch/static/style.css
git commit -m "feat(inride): pause/resume with pause-aware wait accumulator"
```

---

## Task 7: Give Up → prefilled add-spot ride form

**Files:**
- Modify: `hitch/static/inride.js` (`journeyFlow.giveUp`)

**Interfaces:**
- Consumes: `journeyStore.currentWaitMs`; the existing `sessionStorage.rideFormData` prefill convention (see `ride_form.html` `restoreFormData`).
- Produces: `journeyFlow.giveUp()`.

- [ ] **Step 1: Implement giveUp** — prefill wait + pickup into `rideFormData`, clear the journey, navigate to `/ride` (rating stays required there):

```js
// Gave up waiting: hand off to the normal add-spot form, prefilled with the
// pause-aware wait time and the waiting location; the user adds a comment + rating.
journeyFlow.giveUp = function () {
  const j = journeyStore.get(); if (!j) return;
  const waitMin = Math.round(journeyStore.currentWaitMs(j, Date.now()) / 60000);
  sessionStorage.setItem("rideFormData", JSON.stringify({
    pickup_lat: j.pickup.lat, pickup_lon: j.pickup.lon, wait: waitMin,
  }));
  journeyStore.clear();
  journeyUI.teardown();
  window.location.href = "/ride";
};
```

(Confirm the exact keys `ride_form.html:restoreFormData` reads — `pickup_lat/pickup_lon/wait` per the template; adjust if the template uses different keys.)

- [ ] **Step 2: Manual verification:** wait ~2 min, tap **Give Up** → `/ride` opens with the wait field prefilled (~2) and pickup set; the journey is cleared (`inride.journeyStore.get()` → null). Complete + submit → normal success.

- [ ] **Step 3: Commit**

```bash
git add hitch/static/inride.js
git commit -m "feat(inride): Give Up hands off to prefilled add-spot form"
```

---

## Task 8: Got a Ride! slim sheet → in-ride record

**Files:**
- Modify: `hitch/static/inride.js` (`journeyFlow.gotRide`, ride-details sheet)
- Modify: `hitch/static/style.css` (`.inr-sheet`, stars, chips)

**Interfaces:**
- Consumes: `journeyStore.currentWaitMs`.
- Produces: `journeyUI.rideDetailsSheet(onSave)`; `journeyFlow.gotRide(details)`.

- [ ] **Step 1: Build the slim bottom sheet** titled "How was the spot?" with: a 5-star rating (required), vehicle-kind chips (Car default / Truck / Van), signal chips (Thumb / Sign / Asking), an optional comment, a green **Ride On!** button, and a "＋ Add driver / vehicle details" link (opens `/ride` prefilled via `rideFormData`, carrying the sheet's selections + the captured pickup/wait/departure). The sheet reuses the scrim.

- [ ] **Step 2: Implement gotRide** — stamp departure + freeze wait, store details, go in-ride:

```js
// Boarded: departure time = now, wait is frozen (pause-aware), ride details are
// captured; submission is deferred to Finish Ride (destination not known yet).
journeyFlow.gotRide = function (details) {
  const j = journeyStore.get(); if (!j || (j.state !== "waiting")) return;
  j.gotRideMs = Date.now();
  j.finalWaitMs = journeyStore.currentWaitMs(j, j.gotRideMs);
  j.details = details; // {rating, vehicle_kind, signal:[...], comment}
  j.state = "in-ride";
  journeyUI.render(journeyStore.set(j));
};
```

- [ ] **Step 3: Manual verification:** tap **Got a Ride!** → sheet appears; try to save with no stars → blocked; pick 4 stars + Car + Thumb → **Ride On!** → sheet closes, `inride.journeyStore.get()` shows `state:'in-ride'`, `gotRideMs` set, `finalWaitMs` ≈ the waited time, `details` populated.

- [ ] **Step 4: Commit**

```bash
git add hitch/static/inride.js hitch/static/style.css
git commit -m "feat(inride): Got a Ride slim sheet captures rating/details, enters in-ride"
```

---

## Task 9: In-ride UI + Finish Ride (destination GPS + submit)

**Files:**
- Modify: `hitch/static/inride.js` (`in-ride` render, `journeyFlow.finish`, `submitRide`)

**Interfaces:**
- Consumes: `getFixWithRetry`, `setupLocationSelection` (manual-pin fallback), the JSON `/ride` endpoint (Task 2), `journeyStore`.
- Produces: `journeyUI.render` for `in-ride`; `journeyFlow.finish()`; `submitRide(journey, dest): Promise<{ok,d_tag}>`; then hands to `journeyFlow.whatsNext()` (Task 10 stub).

- [ ] **Step 1: In-ride render** — a single orange **Finish Ride** button + a chip `In a ride · HH:MM:SS` from `gotRideMs`. Redraw the pickup pin (grey).

- [ ] **Step 2: `submitRide`** builds the form body from the journey and posts JSON:

```js
function isoLocal(ms) { return new Date(ms).toISOString().slice(0, 16); } // "YYYY-MM-DDTHH:mm"

function submitRide(j, dest) {
  const d = j.details || {};
  const body = new URLSearchParams({
    rate: String(d.rating || ""),
    wait: String(Math.round((j.finalWaitMs || 0) / 60000)),
    signal: (d.signal || []).join(","),
    comment: d.comment || "",
    vehicle_kind: d.vehicle_kind || "",
    pickup_lat: j.pickup.lat, pickup_lon: j.pickup.lon,
    destination_lat: dest.lat, destination_lon: dest.lon,
    datetime_ride: isoLocal(j.gotRideMs),
    arrival_datetime: isoLocal(Date.now()),
  });
  return fetch("/ride", {
    method: "POST", headers: { "X-Requested-With": "inride",
      "Content-Type": "application/x-www-form-urlencoded" }, body,
  }).then((r) => r.json());
}
```

- [ ] **Step 3: `finish`** — capture destination (GPS with retry; manual pin on failure), submit, then What's next:

```js
journeyFlow.finish = function () {
  const j = journeyStore.get(); if (!j || j.state !== "in-ride") return;
  journeyUI.setFinishBusy(true);
  getFixWithRetry().then(
    (dest) => completeFinish(j, dest),
    () => journeyUI.manualPin((dest) => completeFinish(j, dest)) // denied/unavailable → drop a pin
  );
};
function completeFinish(j, dest) {
  submitRide(j, dest).then((res) => {
    journeyUI.setFinishBusy(false);
    if (res && res.ok) { journeyFlow.whatsNext(dest); }
    else { journeyUI.error("Couldn't save the ride — try again."); } // keep in-ride state
  }).catch(() => { journeyUI.setFinishBusy(false); journeyUI.error("Network error — try again."); });
}
```

`journeyUI.manualPin(cb)` wraps `setupLocationSelection` to return a chosen latlng. `whatsNext` is a Task-10 stub that logs `dest`.

- [ ] **Step 4: Manual verification (tunnel, real device):** from in-ride, tap **Finish Ride** → device asks for location; allow → button shows busy ~5s → a ride is created (verify the POST in the Network tab returns `{"ok":true}`); deny location → the manual-pin selection UI appears, confirm → submits. On success the journey is still present until Task 10 (whatsNext stub) — check console.

- [ ] **Step 5: Commit**

```bash
git add hitch/static/inride.js
git commit -m "feat(inride): in-ride bar + Finish Ride (destination GPS w/ retry, JSON submit)"
```

---

## Task 10: What's next? + set-waiting-spot (new leg)

**Files:**
- Modify: `hitch/static/inride.js` (`journeyFlow.whatsNext`, `nextRide`, `end`, set-waiting-spot)

**Interfaces:**
- Consumes: `setupLocationSelection`/`manualPin`, `journeyStore`.
- Produces: `journeyFlow.whatsNext(dropoff)`, `journeyFlow.nextRide(latlng)`, `journeyFlow.end()`.

- [ ] **Step 1: whatsNext dialog** — title "What's next?", **Next Ride** (green) / **End Hitch** (grey). `end()` clears the journey + teardown. **Next Ride** opens set-waiting-spot seeded at the drop-off:

```js
journeyFlow.whatsNext = function (dropoff) {
  journeyUI.dialog({
    title: "What's next?",
    body: "Ride saved — dropped off here. Waiting for another ride from this spot?",
    actions: [
      { label: "Next Ride", cls: "inr-go", onClick: () => journeyUI.setWaitingSpot(dropoff, journeyFlow.nextRide) },
      { label: "End Hitch", cls: "inr-grey", onClick: () => journeyFlow.end() },
    ],
  });
};
journeyFlow.end = function () { journeyStore.clear(); journeyUI.teardown(); };

// New leg: drop-off is the DEFAULT waiting location but the user can move it
// (dropped at an exit, walks to a better spot). Fresh timers; pickup = confirmed pt.
journeyFlow.nextRide = function (latlng) {
  const prev = journeyStore.get();
  const j = journeyStore.set({
    state: "waiting", pickup: { lat: latlng.lat, lon: latlng.lng },
    waitAccumMs: 0, waitSegmentStartMs: Date.now(),
    gotRideMs: null, finalWaitMs: null, details: null,
    legIndex: (prev && prev.legIndex || 0) + 1,
  });
  journeyUI.render(j);
};
```

- [ ] **Step 2: `journeyUI.setWaitingSpot(defaultLatLng, onConfirm)`** — a confirm step (reusing `setupLocationSelection`) with the pin pre-placed at the drop-off, draggable, plus a "Use my location" (calls `getFixWithRetry`) and **Confirm** → `onConfirm(chosenLatLng)`. Title "Where are you waiting?".

- [ ] **Step 3: Manual verification:** finish a ride → "What's next?"; **End Hitch** → all journey chrome gone, `journeyStore.get()` null. Do it again and pick **Next Ride** → "Where are you waiting?" with the pin at the drop-off; move it / Use my location → **Confirm** → a fresh waiting timer starts at the new spot (`legIndex` incremented, `waitAccumMs` 0).

- [ ] **Step 4: Commit**

```bash
git add hitch/static/inride.js
git commit -m "feat(inride): What's next + set-waiting-spot new-leg loop"
```

---

## Task 11: Resume on load

**Files:**
- Modify: `hitch/static/inride.js` (init-on-load; pending-start after login)

**Interfaces:**
- Consumes: everything above.
- Produces: an init routine that runs once the map exists.

- [ ] **Step 1: Init on load.** After `map.js` has created `window.map`, resume:

```js
// Rehydrate on load: restore the docked UI + timer for an in-progress journey.
// Also complete a login round-trip (pendingStart) begun from the soft prompt.
function initInride() {
  const pend = localStorage.getItem(PENDING_KEY);
  if (pend && window.IS_LOGGED_IN) {
    localStorage.removeItem(PENDING_KEY);
    try { const p = JSON.parse(pend); journeyFlow.start(L.latLng(p.lat, p.lon)); } catch (e) {}
  } else if (pend) { localStorage.removeItem(PENDING_KEY); } // returned still anonymous → drop it

  const j = journeyStore.get();
  if (j) journeyUI.render(j); // waiting | paused | in-ride
}
// Run after the map is ready (poll briefly for window.map, or hook map 'load').
if (window.map) initInride();
else { const t = setInterval(() => { if (window.map) { clearInterval(t); initInride(); } }, 100); }
```

- [ ] **Step 2: Old-journey affordance** — if a resumed journey's current segment started > 24h ago, `render` shows a "Welcome back" card (Resume / Discard) before restoring. (Discard = `journeyFlow.end()`.)

- [ ] **Step 3: Manual verification:** start waiting → reload → the bar + correct elapsed timer restore automatically (no console call). In-ride → reload → Finish Ride bar restores. Log out, Start Hitching → Log in → after returning logged-in, you land in `waiting` at the chosen spot. Manually set a journey with an old `waitSegmentStartMs` → reload → "Welcome back" card.

- [ ] **Step 4: Commit**

```bash
git add hitch/static/inride.js
git commit -m "feat(inride): resume in-progress journey on load; complete login round-trip"
```

---

## Task 12: Cover-flow map controls during a journey

**Files:**
- Modify: `hitch/static/map.js` (hide stock map-mode + locate controls while a journey is active; expose current mode)
- Modify: `hitch/static/inride.js` (build the cover-flow stack; wire to `setMapMode`/`toggleHeatmap`/locate)
- Modify: `hitch/static/style.css` (`.inr-cf-collapsed`, `.inr-cf`, tiles, dots) + push zoom up during a journey

**Interfaces:**
- Consumes: `setMapMode`, `toggleHeatmap`, `requestLocationRaw` (the locate action), `mapMode`.
- Produces: `journeyUI.buildControlStack()` / `.destroyControlStack()`; called from `render`/`teardown`.

- [ ] **Step 1: Let inride take over the controls during a journey.** In `map.js`, wrap the stock `mapmode-control` + locate control containers so inride can hide them (add a body class `inride-active`, and CSS `body.inride-active .mapmode-control, body.inride-active .locate-control { display:none }`). Expose `window.requestLocationRaw = requestLocation;` and `window.getMapMode = () => mapMode;`.

- [ ] **Step 2: Build the cover-flow** in `inride.js`: a collapsed single tile (last-used control, default Locate) with a flip-stack hint + layers badge, positioned **above** the zoom (`bottom` set so it clears the zoom, which gets pushed up via `body.inride-active .leaflet-bottom.leaflet-right .leaflet-control-zoom { margin-bottom: … }`). Tap → a 3-D cover-flow of the four original white buttons (Locate `fa-location-crosshairs`, Spots `fa-location-dot`, Heatmap `fa-fire`, Countries `fa-earth-europe`); centre = selection; swipe/tap applies (`setMapMode` / `toggleHeatmap` / `requestLocationRaw`) and collapses onto it. No text labels. Copy the tile/cover-flow CSS from the approved mockup (`scratchpad/stack-coverflow.html` / `inride-mockups.html`).

- [ ] **Step 3: Add `body.inride-active`** toggling in `render` (add) and `teardown` (remove); build/destroy the control stack alongside.

- [ ] **Step 4: Manual verification (touch device):** during waiting/paused/in-ride, the stock switcher+locate are replaced by the collapsed cover-flow tile, which sits **above** the (pushed-up) zoom control — zoom fully visible/tappable. Tap the tile → cover-flow opens above the zoom; swipe to Heatmap → map switches to heatmap and the flow collapses onto the fire tile; open again, tap Locate → map recenters on your location (journey untouched: timers/pins/buttons unchanged). End the journey → stock controls return.

- [ ] **Step 5: Commit**

```bash
git add hitch/static/map.js hitch/static/inride.js hitch/static/style.css
git commit -m "feat(inride): cover-flow map controls during a journey (above the zoom control)"
```

---

## Self-Review notes (author checklist — done)

- **Spec coverage:** choose-action + Log-a-past-ride (T3), soft login (T4), waiting + timer (T5), pause/resume accumulator (T6), Give Up (T7), Got-a-Ride sheet (T8), in-ride + Finish + destination GPS retry + submit (T2/T9), What's next + set-waiting-spot new leg (T10), resume-on-load + login round-trip (T11), cover-flow controls above zoom (T12), discrete-GPS + locate independence (T3/T4/T12), zero-typing data mapping (T9). All covered.
- **No JS test harness:** front-end tasks use documented manual verification via the app + cloudflared tunnel (per the spec's Testing section); the sole backend change (T2) has a pytest.
- **Type consistency:** the `Journey` shape and `journeyStore` / `journeyFlow` / `journeyUI` signatures in the glossary are used identically across tasks; `X-Requested-With: inride` matches between T2 (server) and T9 (client); field names (`rate`, `wait`, `signal`, `datetime_ride`, `arrival_datetime`, `pickup_*`, `destination_*`, `vehicle_kind`) match the `/ride` handler.
- **Open item to confirm during T2/T7:** the exact Nostr-publish function name to monkeypatch and the exact `rideFormData` keys `restoreFormData` reads — both verified by a grep step inside those tasks before coding.
