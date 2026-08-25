# In-ride Drop-off Confirm Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make **Finish Ride** always ask the hitchhiker to confirm the drop-off point on the map, on every leg, instead of silently using a GPS fix.

**Architecture:** Collapse the two near-identical draggable-pin pickers in `inride.js` (`manualPin`, `setWaitingSpot`) into one `journeyUI.pinConfirm` with a single `{lat, lon}` output contract, call it unconditionally from `journeyFlow.finish`, and split "What's next?" into three actions so confirming the drop-off doesn't cost a second map screen mid-sequence.

**Tech Stack:** Vanilla ES5-flavoured JS, Leaflet, `node --test` for the pure helpers, Flask serving `hitch/static/` via a Docker bind mount.

**Spec:** `docs/superpowers/specs/2026-07-25-inride-destination-confirm-design.md`

## Global Constraints

- **Other agents edit this repo concurrently.** Stage only the files named in each task (`git add <paths>`), never `git add -A`. Never `git checkout --`, `git restore`, `git reset --hard`, `git clean`, `git stash`, or `git push --force`. See the banner at the top of `CLAUDE.md`.
- **No headless browser on this host** (`CLAUDE.md`). DOM behaviour is verified by code review plus a manual browser pass; only pure helpers get automated tests.
- **Commit straight to `main`** — no feature branches, no PRs (existing repo convention).
- `hitch/static/` is bind-mounted into the container, so edits go live on save; **no image rebuild needed**.
- `onConfirm` callbacks must **always** receive `{lat, lon}`. Leaflet's `.lng` must never escape a picker.
- Existing test suites must stay green: `node --test tests/` (39 tests) and `python -m pytest tests/ -v`.

## File Structure

| File | Responsibility | Change |
| --- | --- | --- |
| `hitch/static/ride_submit.js` | Pure, Node-testable helpers for the in-ride flow | **Modify** — add + export `toLatLon` |
| `tests/ride_submit.test.js` | Node tests for those helpers | **Modify** — add `toLatLon` cases |
| `hitch/static/inride.js` | Journey state machine + all journey UI | **Modify** — add `pinConfirm`; delete `manualPin` + `setWaitingSpot`; rewrite `finish` and `whatsNext`; normalise coords at `startFromChoose` / `start` / `nextRide` |

---

### Task 1: `toLatLon` coordinate normaliser

The one piece of this change that is pure and therefore properly testable. It exists because `manualPin` returned `{lat, lon}` while `setWaitingSpot` returned a Leaflet `LatLng` — the mismatch documented at `inride.js:860` that once shipped `destination_lon: undefined`.

**Files:**
- Modify: `hitch/static/ride_submit.js` (add function, add to the returned object at `:68`)
- Test: `tests/ride_submit.test.js`

**Interfaces:**
- Consumes: nothing
- Produces: `toLatLon(p) -> {lat: number, lon: number} | null`, exported on `window.RideSubmit` / `module.exports`

- [ ] **Step 1: Write the failing tests**

Append to `tests/ride_submit.test.js`:

```js
test("toLatLon normalises a Leaflet LatLng to {lat, lon}", () => {
  assert.deepStrictEqual(RideSubmit.toLatLon({ lat: 48.2, lng: 16.37 }), { lat: 48.2, lon: 16.37 });
});

test("toLatLon passes a plain {lat, lon} through unchanged", () => {
  assert.deepStrictEqual(RideSubmit.toLatLon({ lat: 48.2, lon: 16.37 }), { lat: 48.2, lon: 16.37 });
});

test("toLatLon prefers lon when an object carries both", () => {
  assert.deepStrictEqual(RideSubmit.toLatLon({ lat: 1, lon: 2, lng: 3 }), { lat: 1, lon: 2 });
});

// Greenwich: lon 0 is falsy, so a `||` fallback would silently read .lng (undefined)
// and submit a ride with no longitude. This is why the implementation uses `!= null`.
test("toLatLon keeps lon 0 rather than falling through to lng", () => {
  assert.deepStrictEqual(RideSubmit.toLatLon({ lat: 51.48, lon: 0 }), { lat: 51.48, lon: 0 });
});

test("toLatLon returns null for a missing point", () => {
  assert.strictEqual(RideSubmit.toLatLon(null), null);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test tests/ride_submit.test.js`
Expected: FAIL — `RideSubmit.toLatLon is not a function`

- [ ] **Step 3: Write the implementation**

In `hitch/static/ride_submit.js`, after `isoLocal`:

```js
  // Accept either a Leaflet LatLng (.lat/.lng) or a plain {lat, lon}, always return
  // {lat, lon}. The in-ride pin pickers used to disagree on this shape, which once
  // produced destination_lon: undefined in a submitted ride body.
  // `!= null` rather than `||`: lon 0 (Greenwich) is falsy but valid.
  function toLatLon(p) {
    if (!p) return null;
    return { lat: p.lat, lon: p.lon != null ? p.lon : p.lng };
  }
```

Change the export line to:

```js
  return { isoLocal, buildFinishBody, buildGiveUpBody, toLatLon };
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `node --test tests/` — Expected: PASS, 44 tests, 0 fail

- [ ] **Step 5: Commit**

```bash
git add hitch/static/ride_submit.js tests/ride_submit.test.js
git commit -m "feat(inride): add toLatLon coordinate normaliser"
```

---

### Task 2: `journeyUI.pinConfirm`, replacing `manualPin`

**Files:**
- Modify: `hitch/static/inride.js` — add `pinConfirm` where `manualPin` lives (`:849-922`), delete `manualPin`, rewrite `journeyFlow.finish` (`:374-422`), alias `toLatLon` near `:109`

**Interfaces:**
- Consumes: `toLatLon` from Task 1
- Produces: `journeyUI.pinConfirm(opts)` where `opts = {title, hint, confirmLabel, seed, color, autoLocate, myLocation, onConfirm, onCancel}`; `onConfirm` receives `{lat, lon}`

- [ ] **Step 1: Verify `ride_submit.js` loads before `inride.js`**

Run: `grep -n "ride_submit.js\|inride.js" hitch/templates/*.html`
Expected: `ride_submit.js` appears first. If not, reorder the tags — `inride.js` aliases `window.RideSubmit` at module-eval time.

- [ ] **Step 2: Alias `toLatLon` beside the existing `buildFinishBody` alias**

After `inride.js:109`:

```js
  const toLatLon = window.RideSubmit.toLatLon;
```

- [ ] **Step 3: Replace `manualPin` with `pinConfirm`**

Delete `manualPin` entirely (`:849-922`) and put this in its place:

```js
    // Unified draggable-pin confirm step. Replaces the two near-identical pickers this
    // file used to carry (manualPin for the drop-off, setWaitingSpot for the next waiting
    // spot) — which had DIFFERENT coordinate output contracts, a mismatch that once
    // shipped destination_lon: undefined to the backend. onConfirm ALWAYS gets {lat, lon}.
    //
    // We cannot reuse map.js's setupLocationSelection(): its confirm writes sessionStorage
    // then redirects to /ride, which would exit the in-ride flow entirely.
    //
    // opts:
    //   title, hint, confirmLabel — card copy (developer constants, not user input)
    //   seed       {lat, lon} | null — initial pin position; null → current map centre
    //   color      "orange" (drop-off) | "green" (waiting spot)
    //   autoLocate bool — request GPS in the background and snap the pin if untouched
    //   myLocation bool — show the "Use my location" button
    //   onConfirm(dest {lat, lon})
    //   onCancel()  — optional
    pinConfirm(opts) {
      if (!window.L || !window.map) {
        // No map (edge case) — never leave the Finish button spinning.
        journeyUI.setFinishBusy(false);
        return;
      }
      // Never stack two pickers: a second card reuses the same button ids and would steal
      // the first card's Confirm/Cancel wiring, leaving the visible buttons dead.
      if (journeyUI._picking) return;
      journeyUI._picking = true;

      const c = window.map.getCenter();
      const seed = opts.seed || { lat: c.lat, lon: c.lng };

      const marker = L.marker([seed.lat, seed.lon], {
        draggable: true,
        icon: L.icon({
          iconUrl: "/static/markers/marker-icon-2x-" + (opts.color || "orange") + ".png",
          shadowUrl: "/static/markers/marker-shadow.png",
          iconSize: [25, 41], iconAnchor: [12, 41],
          popupAnchor: [1, -34], shadowSize: [41, 41],
        }),
      }).addTo(window.map);

      // Once the user has placed the pin themselves, a late GPS fix must never move it —
      // a fix can land 20 s after the picker opens, long after they dragged the pin.
      let touched = false;
      function touch() { touched = true; }
      marker.on("dragstart", touch);

      // Tapping the map repositions the pin (same UX as the main map's location picker).
      function onMapClick(e) { touch(); marker.setLatLng(e.latlng); }
      window.map.on("click", onMapClick);

      // Long-press reposition, routed through inrideOnEntryGesture — exposed ONLY while
      // this picker is open, so a long-press can never drop a pin outside the flow.
      journeyUI._setPin = function (ll) { touch(); marker.setLatLng(ll); };

      const ui = document.createElement("div");
      ui.className = "location-selection-ui";
      ui.innerHTML = [
        "<h4>" + opts.title + "</h4>",
        "<p>" + opts.hint + "</p>",
        '<div class="lsel-actions">',
        // "Use my location" is a positive action — confirm styling so it doesn't read
        // as a dismiss button; only Cancel gets the muted lsel-cancel style.
        opts.myLocation ? '<button class="lsel-confirm" id="inr-pin-myloc">Use my location</button>' : "",
        '<button class="lsel-confirm" id="inr-pin-confirm">' + opts.confirmLabel + "</button>",
        '<button class="lsel-cancel" id="inr-pin-cancel">Cancel</button>',
        "</div>",
      ].join("");
      document.body.appendChild(ui);
      // Neutralize overlay markers (e.g. Hitchwiki event pins) while picking, so a stray
      // tap on one repositions the pin instead of opening its sheet and swallowing the
      // click. See the body.inr-picking rule in style.css.
      document.body.classList.add("inr-picking");

      // One geolocation request shared by the background autoLocate and the button, so
      // tapping "Use my location" mid-flight never starts a second fix.
      let fixPromise = null;
      function requestFix() {
        if (!fixPromise) {
          fixPromise = getFixWithRetry();
          // Drop a failed fix so an explicit tap retries instead of replaying the
          // cached rejection.
          fixPromise.catch(function () { fixPromise = null; });
        }
        return fixPromise;
      }

      const locBtn = document.getElementById("inr-pin-myloc");
      function setLocating(on) {
        if (!locBtn) return;
        locBtn.disabled = on;
        locBtn.textContent = on ? "Locating…" : "Use my location";
      }

      function moveTo(fix) {
        marker.setLatLng([fix.lat, fix.lon]);
        window.map.setView([fix.lat, fix.lon]);
      }

      if (opts.autoLocate) {
        setLocating(true);
        requestFix().then(
          function (fix) { setLocating(false); if (!touched) moveTo(fix); },
          // Silent: the user never asked for this fix, and the pin is already usable.
          function () { setLocating(false); }
        );
      }

      if (locBtn) {
        locBtn.addEventListener("click", function () {
          setLocating(true);
          requestFix().then(
            function (fix) { setLocating(false); touch(); moveTo(fix); },
            function () {
              setLocating(false);
              journeyUI.error("Couldn't get your location — drag the pin instead.");
            }
          );
        });
      }

      function cleanup() {
        window.map.removeLayer(marker);
        window.map.off("click", onMapClick);
        document.body.classList.remove("inr-picking");
        journeyUI._picking = false;
        journeyUI._setPin = null;
        if (ui.parentNode) ui.parentNode.removeChild(ui);
      }

      document.getElementById("inr-pin-confirm").addEventListener("click", function () {
        const ll = marker.getLatLng();
        cleanup();
        // Normalize Leaflet's .lng → .lon so every consumer sees exactly one shape.
        opts.onConfirm(toLatLon(ll));
      });

      document.getElementById("inr-pin-cancel").addEventListener("click", function () {
        cleanup();
        if (opts.onCancel) opts.onCancel();
      });
    },
```

- [ ] **Step 4: Make `journeyFlow.finish` always confirm the drop-off**

In `journeyFlow.finish`, replace the whole `journeyUI.setFinishBusy(true); getFixWithRetry().then(...)` block (`:397-407`) with:

```js
      // Step 1: confirm the drop-off on the map. ALWAYS asked, on every leg including the
      // last one before End Hitch. A silent GPS fix logged the ride wherever the user
      // happened to be when they pressed Finish — often a café hours after arriving — and
      // nothing downstream could tell that apart from a real drop-off. The picker opens
      // instantly and locates in the background, so Finish never blocks on GPS.
      journeyUI.pinConfirm({
        title: "Where did you get out?",
        hint: "Drag the pin or tap the map, then confirm.",
        confirmLabel: "Confirm Drop-off",
        seed: null,
        color: "orange",
        autoLocate: true,
        myLocation: true,
        onConfirm: askAndSubmit,
        // Aborting the picker must not discard the journey: stay in-ride with the button
        // released so Finish can be pressed again.
        onCancel: function () { journeyUI.setFinishBusy(false); },
      });
```

Keep untouched: the `_picking` guard at `:377`, the `finishMs` stamp at `:381`, `askAndSubmit`, and the `finishNudge` branch.

- [ ] **Step 5: Verify no stale references and the suites stay green**

```bash
grep -n "manualPin" hitch/static/*.js          # expect: no output
grep -n "getFixWithRetry" hitch/static/inride.js  # expect: definition + pinConfirm + setWaitingSpot only
node --test tests/
python -m pytest tests/ -q
ruff check
```
Expected: no `manualPin` hits; all tests pass.

- [ ] **Step 6: Commit**

```bash
git add hitch/static/inride.js
git commit -m "feat(inride): always confirm the drop-off location at Finish"
```

---

### Task 3: Migrate `setWaitingSpot` to `pinConfirm` and normalise coordinates

**Files:**
- Modify: `hitch/static/inride.js` — delete `setWaitingSpot` (`:1743-1812`), migrate `startLauncher.open` (`:1860`), normalise `startFromChoose` / `start` / `nextRide`

**Interfaces:**
- Consumes: `journeyUI.pinConfirm` (Task 2), `toLatLon` (Task 1)
- Produces: `journeyFlow.start`, `journeyFlow.nextRide`, `journeyFlow.startFromChoose` accept **either** a Leaflet `LatLng` or `{lat, lon}`

- [ ] **Step 1: Normalise the three journeyFlow entry points**

`startFromChoose` (`:248`) — this one is load-bearing: it stashes the pickup across the login redirect, and with `pinConfirm`'s `{lat, lon}` output the old `latlng.lng` read would store `lon: undefined` and lose the spot.

```js
  journeyFlow.startFromChoose = function (latlng) {
    // Callers pass either a Leaflet LatLng (map.js, entry gestures) or {lat, lon}
    // (pinConfirm). Normalise once here so the redirect stash below can't store
    // lon: undefined and silently lose the chosen spot across login.
    const p = toLatLon(latlng);
    if (window.IS_LOGGED_IN) return journeyFlow.beginWithCoHitchers(p);
```

Then inside, replace both `latlng` uses: the stash becomes
`localStorage.setItem(PENDING_KEY, JSON.stringify({ lat: p.lat, lon: p.lon }));`
and the anonymous action becomes `onClick: () => journeyFlow.beginWithCoHitchers(p)`.

`start` (`:291`) — replace the `pickup` line:

```js
  journeyFlow.start = function (latlng, coHitchhikers) {
    const p = toLatLon(latlng);
    const j = journeyStore.set({
      state: "waiting",
      pickup: { lat: p.lat, lon: p.lon },
```

`nextRide` (`:446`) — same, and drop the now-wrong Leaflet note in its comment:

```js
  journeyFlow.nextRide = function (latlng) {
    const p = toLatLon(latlng);
    const prev = journeyStore.get();
    const j = journeyStore.set({
      state: "waiting", pickup: { lat: p.lat, lon: p.lon },
```

- [ ] **Step 2: Migrate `startLauncher.open` and delete `setWaitingSpot`**

Replace the `journeyUI.setWaitingSpot(...)` call in `startLauncher.open` (`:1860`) with:

```js
      journeyUI.pinConfirm({
        title: "Where are you waiting?",
        hint: "Drag the pin or tap the map, then confirm.",
        confirmLabel: "Confirm",
        // Seeded at the map centre so Confirm is one tap for someone who already panned
        // to where they are; "Use my location" and dragging stay available.
        seed: null,
        color: "green",
        // No background fix here: the user chose this view deliberately, so snapping the
        // pin away from where they panned would fight them.
        autoLocate: false,
        myLocation: true,
        onConfirm: journeyFlow.startFromChoose,
      });
```

Then delete `setWaitingSpot` entirely (`:1743-1812`).

- [ ] **Step 3: Verify**

```bash
grep -n "setWaitingSpot" hitch/static/*.js   # expect: no output
grep -n "\.lng" hitch/static/inride.js       # expect: only inside pinConfirm's seed + toLatLon usage
node --test tests/
```
Expected: no `setWaitingSpot` hits; tests pass.

- [ ] **Step 4: Commit**

```bash
git add hitch/static/inride.js
git commit -m "refactor(inride): fold setWaitingSpot into pinConfirm"
```

---

### Task 4: Split "What's next?" into three actions

Without this, a mid-sequence leg shows two near-identical map pickers back to back — orange drop-off, then green waiting spot, usually on the same point.

**Files:**
- Modify: `hitch/static/inride.js` — `journeyFlow.whatsNext` (`:425-438`)

**Interfaces:**
- Consumes: `journeyUI.pinConfirm` (Task 2), `journeyFlow.nextRide` accepting `{lat, lon}` (Task 3)
- Produces: nothing new

- [ ] **Step 1: Rewrite `whatsNext`**

```js
  // After a ride is saved, ask whether to start another leg or call it a day.
  // `dropoff` is now a point the user confirmed on the map at Finish, not a silent GPS
  // fix — so waiting there needs no second picker. Only actually moving does.
  journeyFlow.whatsNext = function (dropoff) {
    // Clear the in-ride dock, chip, pickup pin, and tick interval so they don't show
    // through behind the dialog. State remains in-ride in the store until nextRide
    // (which calls render) or end (which calls teardown again harmlessly).
    journeyUI.teardown();
    journeyUI.dialog({
      title: "What's next?",
      body: "Ride saved — dropped off here. Waiting for another ride?",
      actions: [
        { label: "Next ride from here", cls: "inr-go", onClick: () => journeyFlow.nextRide(dropoff) },
        {
          label: "Wait somewhere else",
          cls: "inr-ghost",
          // Dropped at a motorway exit and walking to a better on-ramp: the walked-to
          // spot is the one worth logging, so this must stay reachable.
          onClick: () => journeyUI.pinConfirm({
            title: "Where are you waiting?",
            hint: "Drag the pin or tap the map, then confirm.",
            confirmLabel: "Confirm",
            seed: dropoff,
            color: "green",
            // The confirmed drop-off is a better default than a fresh fix.
            autoLocate: false,
            myLocation: true,
            onConfirm: journeyFlow.nextRide,
            // Return to this dialog, or the user is stranded with no way to End Hitch.
            onCancel: () => journeyFlow.whatsNext(dropoff),
          }),
        },
        { label: "End Hitch", cls: "inr-grey", onClick: () => journeyFlow.end() },
      ],
    });
  };
```

- [ ] **Step 2: Verify the dialog can render three actions**

`journeyUI.dialog` iterates an arbitrary `actions` array (`:1695`) and `.inride-dialog .inr-actions` is `display: flex; flex-wrap: wrap` (`style.css:2550`), so three buttons wrap rather than overflow. Confirm both still hold:

```bash
grep -n "flex-wrap" hitch/static/style.css
grep -n "inr-ghost" hitch/static/style.css   # the middle button's style must exist
```

- [ ] **Step 3: Run the suites**

```bash
node --test tests/ && python -m pytest tests/ -q && ruff check
```
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add hitch/static/inride.js
git commit -m "feat(inride): offer next-ride-from-here without a second picker"
```

---

### Task 5: Deploy and hand over for browser verification

**Files:** none modified

- [ ] **Step 1: Confirm the container serves the edited file**

`hitch/static/` is bind-mounted, so no rebuild is needed — but prove it rather than assume:

```bash
curl -s http://localhost:4242/static/inride.js | grep -c "pinConfirm"
```
Expected: a non-zero count. If it is 0, the bind mount isn't what we think — check `docker inspect hitchhiking-map` before going further.

- [ ] **Step 2: Re-check the working tree for other agents' files, then push**

```bash
git status --porcelain     # files you didn't touch may appear — leave them alone
git pull --rebase
git push origin main
```

- [ ] **Step 3: Hand the browser checks to the user**

State plainly that DOM behaviour is unverified by automation (no headless browser on this host per `CLAUDE.md`) and list what to check, after a hard refresh:

1. Finish with GPS granted → orange picker appears immediately, pin snaps to your location.
2. Drag the pin straight away → it does **not** jump when the fix lands.
3. "Use my location" → pin moves; with GPS denied → error toast, pin stays draggable.
4. Cancel the picker → journey still in-ride, Finish works on a second press.
5. Mid-sequence: Finish → "Next ride from here" → waiting dock, no second picker.
6. Mid-sequence: Finish → "Wait somewhere else" → green picker seeded at the drop-off; Cancel returns to "What's next?".
7. Last leg: Finish → drop-off confirm → End Hitch.
8. "Start Hitchhiking" launcher still opens the green picker.
9. Confirm a finished ride lands with two stops and the confirmed destination.

---

## Self-Review

**Spec coverage:** §1 flow change → Task 2 Step 4. §2 unified picker → Tasks 1–3. §3 GPS background/snap-if-untouched → Task 2 Step 3. §4 three-action What's next → Task 4. Error-handling table → Task 2 (no-map guard, cancel semantics, touched guard, silent background failure) and Task 4 (cancel returns to dialog). Testing section → Tasks 1, 5.

**Placeholder scan:** no TBD/TODO; every code step carries real code.

**Type consistency:** `toLatLon` is defined once (Task 1) and used in Tasks 2–3 under that exact name. `pinConfirm`'s option names (`title`, `hint`, `confirmLabel`, `seed`, `color`, `autoLocate`, `myLocation`, `onConfirm`, `onCancel`) are identical across Tasks 2, 3, 4. `onConfirm` receives `{lat, lon}` everywhere; `nextRide` and `startFromChoose` are made to accept that shape in Task 3 before Task 4 relies on it.

**One ordering risk:** Task 4 passes `{lat, lon}` to `nextRide`, which only accepts it after Task 3 Step 1. Tasks must run in order.
