# Driver-Demographic Logging — Phase 2: In-Ride Detail Entry + Live Meters — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a hitchhiker fill in driver/vehicle demographic details **during the ride** via an in-app sheet with two live completeness meters — Save writes onto the journey (submitted at Finish), no page navigation.

**Architecture:** Phase 1 already ships the scoring library (`ride_score.js` `computeScores`), the canonical weights JSON, the `commercial` field, and `buildFinishBody` carry-through. Phase 2 adds: (1) a small Flask route serving the driver-info **choice lists** as JSON so the client sheet can render the same options as the `/ride` form; (2) a shared **details sheet** in `inride.js` that renders the Driver/Vehicle fields with live `computeScores` meters and, on Save, merges the fields onto `j.details`; (3) an **"Add details" affordance + mini-meters** on the in-ride bar, and replacement of the current "Add driver / vehicle details" **`/ride` redirect** with this in-app sheet.

**Tech Stack:** Flask + pytest; vanilla JS (`inride.js` IIFE, `ride_score.js`), `node --test` / `node --check`.

**Design spec:** `docs/superpowers/specs/2026-07-09-driver-demographic-logging-design.md` (§3 shared component, §4 during-ride surface).

## Global Constraints

- **Scoring is display-only and computed** — reuse `window.RideScore.computeScores(fields, weights)`; never hard-code weights (fetch `ride_score_weights.json`).
- **Field names are the canonical `/ride` names** so `buildFinishBody` (Phase 1) already carries them: `driver_reason_to_pick_up` (CSV), `driver_gender`, `driver_age`, `driver_origin_country`, `driver_languages` (CSV), `vehicle_kind`, `vehicle_license_plate_country`, `vehicle_make`, `vehicle_model`, and `commercial` (stored on `j.details.commercial`, a tri-state boolean).
- **Save writes onto the journey, never publishes.** The sheet's Save merges its fields into `j.details` and persists via `journeyStore.set(j)` — no `/ride` POST. Submission still happens only at Finish/Give Up.
- **`make`/`model` are passenger-kind bonus** (`car, van, camper, taxi, motorbike, scooter`) — hide those two inputs when the chosen kind isn't one of these (mirrors `computeScores` bonus gating).
- **`commercial` never inferred from kind** — an explicit Commercial/private toggle (tri-state: unset until the user answers).
- **Age is framed as approximate** — label "Approx. driver age", helper "A rough guess is fine."
- Python: `ruff` line length 130. JS: verify with `node --check`; the DOM sheet has no unit-test surface and is verified on-device.

---

## File Structure

- `hitch/blueprints/main.py` — **modify.** Add a `GET /driver_info_choices.json` route returning the choice lists.
- `tests/test_driver_info_choices_route.py` — **create.** Assert the route's shape.
- `hitch/static/inride.js` — **modify.** Fetch weights+choices once; add `journeyUI.detailsSheet(seed, onSave)`; add mini-meters + "Add details" to the in-ride dock; store `commercial` on `j.details`; replace the "Add driver / vehicle details" `/ride` redirect with `detailsSheet`.
- `hitch/static/style.css` — **modify.** Sheet field/meter styles.

---

### Task 1: Serve the driver-info choice lists as JSON

**Files:**
- Modify: `hitch/blueprints/main.py`
- Test: `tests/test_driver_info_choices_route.py`

**Interfaces:**
- Produces: `GET /driver_info_choices.json` → `{"reasons":[[code,label],…], "genders":[[code,label],…], "languages":[[code,name],…], "countries":[[alpha2,name],…], "plate_countries":[[iso,plate,name],…], "vehicle_kinds":[[kind,emoji],…], "passenger_kinds":[…]}`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_driver_info_choices_route.py`:

```python
def test_driver_info_choices_shape(client):
    resp = client.get("/driver_info_choices.json")
    assert resp.status_code == 200
    assert resp.is_json
    data = resp.get_json()
    for key in ("reasons", "genders", "languages", "countries", "plate_countries", "vehicle_kinds", "passenger_kinds"):
        assert key in data, key
    # Each choice list is a list of pairs/triples; passenger_kinds is a flat list.
    assert ["male", "Male"] in data["genders"]
    assert any(k == "car" for k, _emoji in data["vehicle_kinds"])
    assert "car" in data["passenger_kinds"]
    # commercial-eligible bonus kinds mirror the scoring weights.
    assert set(data["passenger_kinds"]) == {"car", "van", "camper", "taxi", "motorbike", "scooter"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_driver_info_choices_route.py -v`
Expected: FAIL (404 — route not defined).

- [ ] **Step 3: Add the route**

In `hitch/blueprints/main.py`, near the other `main_bp` routes, add (the choice constants are already imported at the top of the file; `json.load` the weights for `passenger_kinds` from the canonical file so it never drifts):

```python
@main_bp.route("/driver_info_choices.json")
def driver_info_choices_json():
    """Choice lists for the in-ride details sheet — same options as the /ride form,
    delivered as JSON so the client renders them without duplicating the data."""
    from hitch.blueprints.utils.ride_score import WEIGHTS

    return jsonify({
        "reasons": REASON_TO_PICK_UP_CHOICES,
        "genders": GENDER_CHOICES,
        "languages": LANGUAGE_CHOICES,
        "countries": COUNTRY_CHOICES,
        "plate_countries": LICENSE_PLATE_COUNTRY_CHOICES,
        "vehicle_kinds": VEHICLE_KIND_CHOICES,
        "passenger_kinds": WEIGHTS["passenger_kinds"],
    })
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_driver_info_choices_route.py -v`
Expected: PASS.

- [ ] **Step 5: ruff + commit**

Run: `ruff check hitch/blueprints/main.py tests/test_driver_info_choices_route.py` (fix if needed).

```bash
git add hitch/blueprints/main.py tests/test_driver_info_choices_route.py
git commit -m "feat(ride): serve driver-info choice lists as JSON for the in-ride sheet"
```

---

### Task 2: Load weights + choices once on the client

**Files:**
- Modify: `hitch/static/inride.js`

**Interfaces:**
- Produces: module-level `_scoreWeights` and `_choices` (both `null` until loaded); `loadDemographicData()` returns a promise that fetches `/ride_score_weights.json` and `/driver_info_choices.json` and caches them; `demographicScores(fields)` → `window.RideScore.computeScores(fields, _scoreWeights)` (returns a zeroed shape if weights not yet loaded).

- [ ] **Step 1: Add the loader near the top of the IIFE** (after the `RideSubmit`/`RideScore` aliases)

```js
  // Weights + choice lists for the in-ride details sheet, fetched once. Kept module-level
  // so the sheet can render and score synchronously after load. Both are small and cached
  // by the browser; failures leave the sheet usable with empty pickers.
  let _scoreWeights = null;
  let _choices = null;
  function loadDemographicData() {
    const w = _scoreWeights
      ? Promise.resolve(_scoreWeights)
      : fetch("/ride_score_weights.json").then(function (r) { return r.json(); }).then(function (j) { _scoreWeights = j; }).catch(function () {});
    const c = _choices
      ? Promise.resolve(_choices)
      : fetch("/driver_info_choices.json").then(function (r) { return r.json(); }).then(function (j) { _choices = j; }).catch(function () {});
    return Promise.all([w, c]);
  }
  function demographicScores(fields) {
    if (!_scoreWeights || !window.RideScore) {
      return { driver: { pct: 0 }, vehicle: { pct: 0, bonusEligible: false }, total: 0 };
    }
    return window.RideScore.computeScores(fields, _scoreWeights);
  }
```

- [ ] **Step 2: Kick off the load on module init**

Find where the IIFE runs its on-load work (the `initInride`/resume block near the bottom that reads `journeyStore`). Add a non-blocking `loadDemographicData();` call there so weights+choices are ready by the time the user reaches the sheet.

- [ ] **Step 3: Verify it parses**

Run: `node --check hitch/static/inride.js`
Expected: OK.

- [ ] **Step 4: Commit**

```bash
git add hitch/static/inride.js
git commit -m "feat(inride): fetch score weights + driver-info choices once on load"
```

---

### Task 3: The in-ride details sheet (fields + live meters + Save)

**Files:**
- Modify: `hitch/static/inride.js`
- Modify: `hitch/static/style.css`

**Interfaces:**
- Consumes: `_choices`, `demographicScores`, `journeyStore`.
- Produces: `journeyUI.detailsSheet(seed, onSave)` — opens a bottom sheet seeded from `seed` (an object of the canonical fields, e.g. the current `j.details`), renders Driver + Vehicle blocks with two live meters, and calls `onSave(fields)` with the merged canonical fields when the user taps Save. Dismiss (× / scrim) closes without saving.

This is DOM/browser code with no unit-test surface; verified with `node --check` plus the on-device steps at the end.

- [ ] **Step 1: Add `detailsSheet` to `journeyUI`** (near `rideDetailsSheet`). Reuses `.inr-sheet` / `.inride-scrim` / `.inr-field` / `.inr-chips` / `.inr-optchip` chrome from Phase-1 sheets.

```js
    // In-ride driver/vehicle detail entry with two live completeness meters. Seeded
    // from the current details; onSave(fields) fires on Save with the canonical field
    // names. NOT a submission — the caller merges the result onto the journey.
    detailsSheet(seed, onSave) {
      if (journeyUI._openDialog) journeyUI._openDialog.close();
      const ch = _choices || { reasons: [], genders: [], languages: [], countries: [], vehicle_kinds: [], passenger_kinds: [] };
      // Working copy of the fields, seeded from `seed`.
      const f = {
        driver_reason_to_pick_up: (seed.driver_reason_to_pick_up || []).slice(),
        driver_gender: seed.driver_gender || "",
        driver_age: (seed.driver_age === 0 || seed.driver_age) ? seed.driver_age : "",
        driver_origin_country: seed.driver_origin_country || "",
        driver_languages: (seed.driver_languages || []).slice(),
        vehicle_kind: seed.vehicle_kind || "",
        commercial: seed.commercial === true || seed.commercial === false ? seed.commercial : null,
        vehicle_license_plate_country: seed.vehicle_license_plate_country || "",
        vehicle_make: seed.vehicle_make || "",
        vehicle_model: seed.vehicle_model || "",
      };

      const scrim = document.createElement("div");
      scrim.className = "inride-scrim";
      const sheet = document.createElement("div");
      sheet.className = "inr-sheet inr-sheet--scroll";

      const grab = document.createElement("div"); grab.className = "inr-sheet__grab"; sheet.appendChild(grab);
      const closeX = document.createElement("button");
      closeX.type = "button"; closeX.className = "inr-sheet__close"; closeX.setAttribute("aria-label", "Close");
      closeX.innerHTML = "&times;"; closeX.addEventListener("click", function () { close(); });
      sheet.appendChild(closeX);

      const titleEl = document.createElement("h4"); titleEl.textContent = "Driver & vehicle details"; sheet.appendChild(titleEl);

      // ── Two live meters ────────────────────────────────────────────────────
      const meters = document.createElement("div"); meters.className = "inr-meters";
      const dMeter = makeMeter("Driver"); const vMeter = makeMeter("Vehicle");
      meters.appendChild(dMeter.el); meters.appendChild(vMeter.el); sheet.appendChild(meters);
      function refreshMeters() {
        const s = demographicScores(f);
        dMeter.set(s.driver.pct); vMeter.set(s.vehicle.pct);
        makeModelWrap.style.display = (ch.passenger_kinds.indexOf(f.vehicle_kind) !== -1) ? "" : "none";
      }
      function makeMeter(label) {
        const el = document.createElement("div"); el.className = "inr-meter";
        const l = document.createElement("span"); l.className = "inr-meter__label"; l.textContent = label;
        const barWrap = document.createElement("div"); barWrap.className = "inr-meter__track";
        const bar = document.createElement("div"); bar.className = "inr-meter__fill"; barWrap.appendChild(bar);
        const pct = document.createElement("span"); pct.className = "inr-meter__pct";
        el.appendChild(l); el.appendChild(barWrap); el.appendChild(pct);
        return { el: el, set: function (p) { bar.style.width = p + "%"; pct.textContent = p + "%"; } };
      }

      // ── Field builders (chips single/multi, stepper, searchable select) ──────
      function fieldWrap(labelText) {
        const w = document.createElement("div"); w.className = "inr-field";
        const l = document.createElement("label"); l.textContent = labelText; w.appendChild(l);
        return w;
      }
      // Single-select chips (gender). choices: [[code,label],…]
      function chipSingle(w, choices, getVal, setVal) {
        const row = document.createElement("div"); row.className = "inr-chips";
        choices.forEach(function (pair) {
          const b = document.createElement("button"); b.type = "button"; b.className = "inr-optchip";
          b.textContent = pair[1]; b.setAttribute("data-code", pair[0]);
          if (getVal() === pair[0]) b.classList.add("inr-optchip--on");
          b.addEventListener("click", function () {
            setVal(getVal() === pair[0] ? "" : pair[0]); // tap again clears
            row.querySelectorAll(".inr-optchip").forEach(function (c) {
              c.classList.toggle("inr-optchip--on", c.getAttribute("data-code") === getVal());
            });
            refreshMeters();
          });
          row.appendChild(b);
        });
        w.appendChild(row);
      }
      // Multi-select chips (reasons, languages). arr is the working array of codes.
      function chipMulti(w, choices, arr) {
        const row = document.createElement("div"); row.className = "inr-chips";
        choices.forEach(function (pair) {
          const b = document.createElement("button"); b.type = "button"; b.className = "inr-optchip"; b.textContent = pair[1];
          if (arr.indexOf(pair[0]) !== -1) b.classList.add("inr-optchip--on");
          b.addEventListener("click", function () {
            const i = arr.indexOf(pair[0]);
            if (i === -1) { arr.push(pair[0]); b.classList.add("inr-optchip--on"); }
            else { arr.splice(i, 1); b.classList.remove("inr-optchip--on"); }
            refreshMeters();
          });
          row.appendChild(b);
        });
        w.appendChild(row);
      }
      // Searchable select for long lists (country, plate country). choices pairs [code,name].
      function searchSelect(w, choices, placeholder, getVal, setVal) {
        const input = document.createElement("input"); input.type = "text"; input.className = "inr-cohitch-input";
        input.placeholder = placeholder; input.setAttribute("autocomplete", "off");
        const cur = choices.find(function (p) { return p[0] === getVal(); });
        if (cur) input.value = cur[1];
        const list = document.createElement("ul"); list.className = "inr-cohitch-suggest"; list.style.display = "none";
        const wrap = document.createElement("div"); wrap.className = "inr-cohitch-inputwrap";
        wrap.appendChild(input); wrap.appendChild(list); w.appendChild(wrap);
        input.addEventListener("input", function () {
          const q = input.value.trim().toLowerCase();
          list.innerHTML = "";
          if (!q) { list.style.display = "none"; setVal(""); refreshMeters(); return; }
          choices.filter(function (p) { return p[1].toLowerCase().indexOf(q) !== -1; }).slice(0, 8).forEach(function (p) {
            const li = document.createElement("li"); li.textContent = p[1];
            li.addEventListener("mousedown", function (e) { e.preventDefault(); input.value = p[1]; setVal(p[0]); list.style.display = "none"; refreshMeters(); });
            list.appendChild(li);
          });
          list.style.display = list.children.length ? "block" : "none";
        });
      }

      // ── Driver block ─────────────────────────────────────────────────────────
      const reasonF = fieldWrap("Why did they pick you up?"); chipMulti(reasonF, ch.reasons, f.driver_reason_to_pick_up); sheet.appendChild(reasonF);
      const genderF = fieldWrap("Driver gender"); chipSingle(genderF, ch.genders, function () { return f.driver_gender; }, function (v) { f.driver_gender = v; }); sheet.appendChild(genderF);
      const ageF = fieldWrap("Approx. driver age");
      const ageHelp = document.createElement("div"); ageHelp.className = "inr-field__help"; ageHelp.textContent = "A rough guess is fine."; ageF.appendChild(ageHelp);
      const age = document.createElement("input"); age.type = "number"; age.min = "0"; age.max = "120"; age.className = "inr-cohitch-input"; age.inputMode = "numeric";
      if (f.driver_age !== "") age.value = f.driver_age;
      age.addEventListener("input", function () { f.driver_age = age.value === "" ? "" : parseInt(age.value, 10); refreshMeters(); });
      ageF.appendChild(age); sheet.appendChild(ageF);
      const originF = fieldWrap("Driver's country"); searchSelect(originF, ch.countries, "Search country…", function () { return f.driver_origin_country; }, function (v) { f.driver_origin_country = v; }); sheet.appendChild(originF);
      const langF = fieldWrap("Languages spoken"); chipMulti(langF, ch.languages, f.driver_languages); sheet.appendChild(langF);

      // ── Vehicle block ────────────────────────────────────────────────────────
      const kindF = fieldWrap("Vehicle");
      chipSingle(kindF, ch.vehicle_kinds.map(function (p) { return [p[0], p[1] + " " + p[0]]; }), function () { return f.vehicle_kind; }, function (v) { f.vehicle_kind = v; });
      sheet.appendChild(kindF);
      // Commercial tri-state toggle (Yes / No — unset until answered).
      const commF = fieldWrap("Commercial driver?");
      chipSingle(commF, [["yes", "Commercial"], ["no", "Private"]],
        function () { return f.commercial === true ? "yes" : (f.commercial === false ? "no" : ""); },
        function (v) { f.commercial = v === "yes" ? true : (v === "no" ? false : null); });
      sheet.appendChild(commF);
      const plateF = fieldWrap("Number-plate country"); searchSelect(plateF, ch.countries, "Search country…", function () { return f.vehicle_license_plate_country; }, function (v) { f.vehicle_license_plate_country = v; }); sheet.appendChild(plateF);
      // make/model — passenger vehicles only (bonus). Hidden for other kinds by refreshMeters().
      const makeModelWrap = document.createElement("div");
      const makeF = fieldWrap("Make"); const make = document.createElement("input"); make.type = "text"; make.className = "inr-cohitch-input"; make.value = f.vehicle_make; make.addEventListener("input", function () { f.vehicle_make = make.value; refreshMeters(); }); makeF.appendChild(make); makeModelWrap.appendChild(makeF);
      const modelF = fieldWrap("Model"); const model = document.createElement("input"); model.type = "text"; model.className = "inr-cohitch-input"; model.value = f.vehicle_model; model.addEventListener("input", function () { f.vehicle_model = model.value; refreshMeters(); }); modelF.appendChild(model); makeModelWrap.appendChild(modelF);
      sheet.appendChild(makeModelWrap);

      const saveBtn = document.createElement("button");
      saveBtn.type = "button"; saveBtn.className = "inr-big inr-big--green inr-sheet__save";
      saveBtn.innerHTML = '<i class="fa-solid fa-check"></i> Save details';
      saveBtn.addEventListener("click", function () { close(); onSave(f); });
      sheet.appendChild(saveBtn);

      function close() {
        if (scrim.parentNode) scrim.parentNode.removeChild(scrim);
        if (sheet.parentNode) sheet.parentNode.removeChild(sheet);
        journeyUI._openDialog = null;
      }
      scrim.addEventListener("click", close);
      document.body.appendChild(scrim); document.body.appendChild(sheet);
      journeyUI._openDialog = { close };
      refreshMeters();
      return { close };
    },
```

- [ ] **Step 2: Add sheet + meter CSS** to `hitch/static/style.css`:

```css
.inr-sheet--scroll { max-height: 82vh; overflow-y: auto; }
.inr-field__help { font-size: 12px; color: #888; margin: -2px 0 6px; }
.inr-meters { display: flex; gap: 12px; margin: 4px 0 12px; }
.inr-meter { flex: 1; }
.inr-meter__label { font-size: 12px; font-weight: 600; color: #555; }
.inr-meter__track { height: 8px; background: #eee; border-radius: 4px; overflow: hidden; margin: 3px 0; }
.inr-meter__fill { height: 100%; background: #1a9850; border-radius: 4px; transition: width .2s ease; }
.inr-meter__pct { font-size: 11px; color: #777; }
```

- [ ] **Step 3: Verify it parses**

Run: `node --check hitch/static/inride.js`
Expected: OK.

- [ ] **Step 4: Commit**

```bash
git add hitch/static/inride.js hitch/static/style.css
git commit -m "feat(inride): in-ride driver/vehicle details sheet with live completeness meters"
```

---

### Task 4: Wire the sheet into the ride — in-ride bar meters + replace the /ride redirect

**Files:**
- Modify: `hitch/static/inride.js`

**Interfaces:**
- Consumes: `journeyUI.detailsSheet`, `journeyStore`, `demographicScores`.
- Produces: an "Add details" affordance + mini-meters on the in-ride dock; the "Got a Ride!" sheet's "Add driver / vehicle details" link opens `detailsSheet` instead of redirecting to `/ride`; Save merges the fields onto `j.details`.

- [ ] **Step 1: Replace the "Add driver / vehicle details" redirect** in `rideDetailsSheet`. The current handler stashes `rideFormData` and does `window.location.href = "/ride"`. Replace its body so it opens the in-app sheet, seeded from the sheet's current selections, and folds the result back into the "Got a Ride!" sheet's outgoing details on Save:

```js
      moreLink.addEventListener("click", function (e) {
        e.preventDefault();
        // Seed from what's already chosen on this sheet (rating/kind live in outer scope).
        const seed = Object.assign({ vehicle_kind: vehicleKind }, journeyUI._pendingDetails || {});
        journeyUI.detailsSheet(seed, function (fields) {
          journeyUI._pendingDetails = fields; // merged into details on Ride On!
        });
      });
```

And where `rideDetailsSheet`'s "Ride On!" builds the `details` object passed to `onSave`, merge `journeyUI._pendingDetails` into it (so demographics entered via the sheet reach `gotRide` → `j.details`), then clear `journeyUI._pendingDetails`.

- [ ] **Step 2: Add "Add details" + mini-meters to the in-ride dock** in `_renderInRide`. After the Finish button is appended, add a compact row: two mini-meters (from `demographicScores(j.details || {})`) and an "Add details" button that opens `detailsSheet(j.details || {}, …)` and, on Save, merges onto `j.details`:

```js
      // Demographic entry during the ride: mini-meters + an "Add details" button that
      // opens the details sheet. Save merges onto j.details (submitted at Finish).
      const demoRow = document.createElement("div");
      demoRow.className = "inr-demo-row";
      const s = demographicScores(j.details || {});
      demoRow.innerHTML =
        '<span class="inr-demo-meter">Driver ' + s.driver.pct + '%</span>' +
        '<span class="inr-demo-meter">Vehicle ' + s.vehicle.pct + '%</span>';
      const addBtn = document.createElement("button");
      addBtn.type = "button"; addBtn.className = "inr-demo-add";
      addBtn.innerHTML = '<i class="fa-solid fa-plus"></i> Add details';
      addBtn.addEventListener("click", function () {
        journeyUI.detailsSheet(j.details || {}, function (fields) {
          const cur = journeyStore.get(); if (!cur) return;
          cur.details = Object.assign({}, cur.details, fields);
          journeyStore.set(cur);
          journeyUI.render(cur); // re-render so the mini-meters update
        });
      });
      demoRow.appendChild(addBtn);
      dock.appendChild(demoRow);
```

(Add matching `.inr-demo-row` / `.inr-demo-meter` / `.inr-demo-add` CSS — small pill row above/below the Finish button.)

- [ ] **Step 3: Verify it parses + no leftover redirect**

Run: `node --check hitch/static/inride.js && grep -n 'window.location.href = "/ride"' hitch/static/inride.js`
Expected: parses OK; the grep no longer matches inside `rideDetailsSheet`'s "add details" handler (only the Give-Up/other legitimate redirects, if any, remain — confirm the moreLink one is gone).

- [ ] **Step 4: On-device verification** (no unit-test surface)

1. Start a ride → **Got a Ride!** → tap **"＋ Add driver / vehicle details"**: the in-app sheet opens (no page navigation), fields render, meters update live as you fill them.
2. Save → back on the Got-a-Ride sheet → **Ride On!**: proceed to in-ride.
3. In-ride bar shows Driver/Vehicle mini-meters; **Add details** opens the sheet seeded with what you entered; Save updates the mini-meters.
4. **Finish** the ride (in test mode) and confirm the submitted body carries the demographic fields (console-logged by the test-mode dry-run) — `driver_gender`, `driver_age`, `commercial`, etc.
5. make/model inputs are hidden when the kind isn't a passenger vehicle (e.g. `truck`), shown for `car`.

- [ ] **Step 5: Commit**

```bash
git add hitch/static/inride.js hitch/static/style.css
git commit -m "feat(inride): add in-ride details entry (meters + Add details) and drop the /ride redirect"
```

---

## Self-Review

- **Spec coverage (Phase 2):** in-ride bar mini-meters + Add details (Task 4) ✓; shared details sheet with live meters (Task 3) ✓; Save-onto-journey, no publish (Tasks 3–4) ✓; make/model passenger-only gating (Task 3 `refreshMeters`) ✓; commercial explicit toggle (Task 3) ✓; replaces the `/ride` redirect (Task 4) ✓; choice lists match the `/ride` form (Task 1) ✓. Vehicle-kind expand (spec §6) is folded into the kind chip-single here (all kinds shown); a separate "＋ More" collapse can be a follow-up if the full list is too long.
- **Placeholder scan:** none — each step has concrete code/commands. (Task 4 Steps 1–2 reference the surrounding `rideDetailsSheet`/`_renderInRide` code by name; the implementer edits in place.)
- **Type consistency:** field names identical to Phase 1's `buildFinishBody` keys and the `/ride` handler; `commercial` is the tri-state boolean stored on `j.details`; `computeScores(fields, weights)` return shape (`driver.pct`/`vehicle.pct`) used consistently.

## Deferred to later phases (per spec)
Phase 3 (completion enrich sheet), Phase 4 (historic `/ride` form restyle with the shared component), Phase 5 (post-hitching "Your rides" + per-user score/level/streak). This plan is the during-ride surface only.
