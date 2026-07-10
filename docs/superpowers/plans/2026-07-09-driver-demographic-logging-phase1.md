# Driver-Demographic Logging — Phase 1: Scoring Foundation & Carry-Through — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish the shared completeness-scoring library and make the in-ride Finish flow carry every driver/vehicle demographic field (plus a new `commercial` toggle) end-to-end into the persisted Nostr ride — the data + scoring foundation the later UI phases build on.

**Architecture:** A single canonical weights JSON (`hitch/static/ride_score_weights.json`) is read by both a browser-and-Node JS module (`ride_score.js`, pure `computeScores`) and a Python mirror (`ride_score.py`). The `commercial` flag is added as an optional key inside the existing `mode_of_transportation` **JSON** column (no schema change). The pure `/ride` body builder is extracted from the `inride.js` IIFE into a testable `ride_submit.js` and extended to carry all demographic fields.

**Tech Stack:** Vanilla JS (dual CommonJS/browser module, `node --test` runner — Node v22), Flask + pydantic, pytest.

**Design spec:** `docs/superpowers/specs/2026-07-09-driver-demographic-logging-design.md`

## Global Constraints

- **No structural DB changes.** `commercial` is a new key inside the `mode_of_transportation` JSON; scores are computed, never stored.
- **Canonical scoring weights (base scale = 100):**
  - Driver: `driver_reason_to_pick_up` 15, `driver_gender` 15, `driver_age` 10, `driver_origin_country` 10, `driver_languages` 10 (max 60).
  - Vehicle base: `vehicle_license_plate_country` 20, `vehicle_kind` 10, `commercial` 10 (max 40).
  - Vehicle bonus (passenger kinds only): `vehicle_make` 5, `vehicle_model` 5 (→ max 110 total).
- **`PASSENGER_KINDS` = `{car, van, camper, taxi, motorbike, scooter}`** — make/model only apply (score + display) for these `vehicle_kind` values.
- **`vehicle_license_plate_identifier` is never scored** (PII).
- **Weights live only in `ride_score_weights.json`** — both JS and Python read that file; neither hard-codes the numbers.
- Field names are the canonical `/ride` form names throughout (`driver_reason_to_pick_up`, `driver_gender`, `driver_age`, `driver_origin_country`, `driver_languages`, `vehicle_kind`, `vehicle_license_plate_country`, `vehicle_make`, `vehicle_model`) plus `vehicle_commercial` (form/transport field) ↔ `commercial` (JSON key).
- Python style: `ruff` line length 130.

---

## File Structure

- `hitch/static/ride_score_weights.json` — **create.** Canonical weights + passenger kinds.
- `hitch/static/ride_score.js` — **create.** Pure `computeScores(fields, weights)`; dual browser/CommonJS export.
- `hitch/blueprints/utils/ride_score.py` — **create.** Loads the JSON; `score_fields(fields)` Python mirror.
- `hitch/static/ride_submit.js` — **create.** `isoLocal` + `buildFinishBody` extracted from `inride.js`, extended for demographics; dual export.
- `hitch/blueprints/utils/hitchhiking_data_standard_pydantic_model.py:92-97` — **modify.** Add `commercial` to `ModeOfTranportation`.
- `hitch/blueprints/publish_ride.py:153-164` — **modify.** Thread `vehicle_commercial` into `ModeOfTranportation`.
- `hitch/blueprints/main.py` — **modify.** Parse `vehicle_commercial` on POST; read it back on GET edit-prefill.
- `hitch/static/inride.js:93-120` — **modify.** Remove local `isoLocal`/`buildFinishBody`; call `RideSubmit`.
- `hitch/templates/map.html:46` — **modify.** Load `ride_score.js` + `ride_submit.js` before `inride.js`.
- Tests: `tests/ride_score.test.js`, `tests/ride_submit.test.js` (node), `tests/test_ride_score.py`, `tests/test_commercial_field.py`, `tests/test_inride_demographics.py` (pytest).

---

### Task 1: Canonical weights JSON + JS scoring library

**Files:**
- Create: `hitch/static/ride_score_weights.json`
- Create: `hitch/static/ride_score.js`
- Test: `tests/ride_score.test.js`

**Interfaces:**
- Produces: `RideScore.computeScores(fields, weights) -> { driver:{earned,max,pct,missing:[{field,pts}]}, vehicle:{earned,max,pct,missing:[{field,pts}],bonusEligible}, total }`. `weights` is the parsed `ride_score_weights.json`. In the browser the module is `window.RideScore`; under Node it is `module.exports`.

- [ ] **Step 1: Write the canonical weights file**

Create `hitch/static/ride_score_weights.json`:

```json
{
  "driver": {
    "driver_reason_to_pick_up": 15,
    "driver_gender": 15,
    "driver_age": 10,
    "driver_origin_country": 10,
    "driver_languages": 10
  },
  "vehicle_base": {
    "vehicle_license_plate_country": 20,
    "vehicle_kind": 10,
    "commercial": 10
  },
  "vehicle_bonus": {
    "vehicle_make": 5,
    "vehicle_model": 5
  },
  "passenger_kinds": ["car", "van", "camper", "taxi", "motorbike", "scooter"]
}
```

- [ ] **Step 2: Write the failing test**

Create `tests/ride_score.test.js`:

```js
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const RideScore = require("../hitch/static/ride_score.js");
const WEIGHTS = JSON.parse(
  fs.readFileSync(path.join(__dirname, "../hitch/static/ride_score_weights.json"), "utf8")
);

test("empty ride scores zero on both meters", () => {
  const s = RideScore.computeScores({}, WEIGHTS);
  assert.strictEqual(s.driver.earned, 0);
  assert.strictEqual(s.driver.max, 60);
  assert.strictEqual(s.driver.pct, 0);
  assert.strictEqual(s.vehicle.earned, 0);
  // No kind chosen -> not passenger -> make/model excluded -> base-only max 40.
  assert.strictEqual(s.vehicle.max, 40);
  assert.strictEqual(s.vehicle.bonusEligible, false);
});

test("full driver detail earns 60 and 100%", () => {
  const s = RideScore.computeScores({
    driver_reason_to_pick_up: ["curiosity"],
    driver_gender: "female",
    driver_age: 34,
    driver_origin_country: "DE",
    driver_languages: ["deu", "eng"],
  }, WEIGHTS);
  assert.strictEqual(s.driver.earned, 60);
  assert.strictEqual(s.driver.pct, 100);
  assert.deepStrictEqual(s.driver.missing, []);
});

test("commercial=false still counts as answered", () => {
  const s = RideScore.computeScores({ vehicle_kind: "bus", commercial: false }, WEIGHTS);
  // bus not passenger -> max 40 (kind 10 + commercial 10 + plate 20)
  assert.strictEqual(s.vehicle.max, 40);
  assert.strictEqual(s.vehicle.earned, 20); // kind 10 + commercial 10
  assert.strictEqual(s.vehicle.bonusEligible, false);
});

test("passenger kind unlocks make/model bonus in max and missing", () => {
  const s = RideScore.computeScores({ vehicle_kind: "car" }, WEIGHTS);
  assert.strictEqual(s.vehicle.bonusEligible, true);
  assert.strictEqual(s.vehicle.max, 50); // 40 base + 10 bonus
  assert.strictEqual(s.vehicle.earned, 10); // kind only
  // Missing ordered by points desc; plate country (20) first.
  assert.deepStrictEqual(
    s.vehicle.missing.map((m) => m.field),
    ["vehicle_license_plate_country", "commercial", "vehicle_make", "vehicle_model"]
  );
});

test("total sums driver + vehicle earned including bonus", () => {
  const s = RideScore.computeScores({
    driver_reason_to_pick_up: ["curiosity"], // 15
    vehicle_kind: "car",                     // 10
    vehicle_make: "Toyota",                  // +5 bonus
  }, WEIGHTS);
  assert.strictEqual(s.total, 30);
});
```

- [ ] **Step 3: Run test to verify it fails**

Run: `node --test tests/ride_score.test.js`
Expected: FAIL — `Cannot find module '../hitch/static/ride_score.js'`.

- [ ] **Step 4: Write the scoring module**

Create `hitch/static/ride_score.js`:

```js
// Pure completeness-scoring library shared by the browser (window.RideScore) and
// Node tests (module.exports). Weights are supplied by the caller from the single
// canonical source hitch/static/ride_score_weights.json — never hard-coded here.
(function (root, factory) {
  const mod = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = mod;
  else root.RideScore = mod;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // A field is "filled" when the user has supplied a real answer. Arrays need a
  // non-empty entry; strings need non-whitespace; age accepts a number or numeric
  // string; commercial is a tri-state where BOTH true and false count as answered
  // (only null/undefined is unanswered).
  function isFilled(field, value) {
    if (field === "commercial") return value === true || value === false;
    if (Array.isArray(value)) return value.length > 0;
    if (field === "driver_age") return value !== null && value !== undefined && String(value).trim() !== "";
    return typeof value === "string" && value.trim() !== "";
  }

  function scoreGroup(fields, weightMap) {
    let earned = 0, max = 0;
    const missing = [];
    for (const field of Object.keys(weightMap)) {
      const pts = weightMap[field];
      max += pts;
      if (isFilled(field, fields[field])) earned += pts;
      else missing.push({ field: field, pts: pts });
    }
    return { earned, max, missing };
  }

  function computeScores(fields, weights) {
    fields = fields || {};
    const driver = scoreGroup(fields, weights.driver);
    const driverPct = driver.max ? Math.round((driver.earned / driver.max) * 100) : 0;

    const base = scoreGroup(fields, weights.vehicle_base);
    const bonusEligible = weights.passenger_kinds.indexOf(fields.vehicle_kind) !== -1;
    let vEarned = base.earned, vMax = base.max;
    const vMissing = base.missing.slice();
    if (bonusEligible) {
      const bonus = scoreGroup(fields, weights.vehicle_bonus);
      vEarned += bonus.earned;
      vMax += bonus.max;
      for (const m of bonus.missing) vMissing.push(m);
    }
    // Highest-value missing first, so nudges surface the biggest wins.
    vMissing.sort((a, b) => b.pts - a.pts);
    driver.missing.sort((a, b) => b.pts - a.pts);
    const vPct = vMax ? Math.round((vEarned / vMax) * 100) : 0;

    return {
      driver: { earned: driver.earned, max: driver.max, pct: driverPct, missing: driver.missing },
      vehicle: { earned: vEarned, max: vMax, pct: vPct, missing: vMissing, bonusEligible: bonusEligible },
      total: driver.earned + vEarned,
    };
  }

  return { computeScores };
});
```

- [ ] **Step 5: Run test to verify it passes**

Run: `node --test tests/ride_score.test.js`
Expected: PASS (5 tests).

- [ ] **Step 6: Commit**

```bash
git add hitch/static/ride_score_weights.json hitch/static/ride_score.js tests/ride_score.test.js
git commit -m "feat(score): canonical weights + computeScores JS library"
```

---

### Task 2: Python scoring mirror

**Files:**
- Create: `hitch/blueprints/utils/ride_score.py`
- Test: `tests/test_ride_score.py`

**Interfaces:**
- Consumes: `hitch/static/ride_score_weights.json` (same file as Task 1).
- Produces: `ride_score.WEIGHTS` (dict), `ride_score.PASSENGER_KINDS` (set), `ride_score.score_fields(fields: dict) -> dict` mirroring `computeScores` (same keys: `driver`, `vehicle`, `total`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_ride_score.py`:

```python
from hitch.blueprints.utils import ride_score


def test_weights_match_the_canonical_scale():
    # Guards accidental edits to the shared weights file.
    assert ride_score.WEIGHTS["driver"]["driver_reason_to_pick_up"] == 15
    assert ride_score.WEIGHTS["vehicle_base"]["vehicle_license_plate_country"] == 20
    assert sum(ride_score.WEIGHTS["driver"].values()) == 60
    assert sum(ride_score.WEIGHTS["vehicle_base"].values()) == 40
    assert ride_score.PASSENGER_KINDS == {"car", "van", "camper", "taxi", "motorbike", "scooter"}


def test_full_driver_scores_60():
    s = ride_score.score_fields({
        "driver_reason_to_pick_up": ["curiosity"],
        "driver_gender": "female",
        "driver_age": 34,
        "driver_origin_country": "DE",
        "driver_languages": ["deu"],
    })
    assert s["driver"]["earned"] == 60
    assert s["driver"]["pct"] == 100


def test_commercial_false_is_answered_and_bus_excludes_bonus():
    s = ride_score.score_fields({"vehicle_kind": "bus", "commercial": False})
    assert s["vehicle"]["earned"] == 20
    assert s["vehicle"]["max"] == 40
    assert s["vehicle"]["bonus_eligible"] is False


def test_passenger_kind_unlocks_bonus():
    s = ride_score.score_fields({"vehicle_kind": "car", "vehicle_make": "Toyota"})
    assert s["vehicle"]["bonus_eligible"] is True
    assert s["vehicle"]["max"] == 50
    assert s["vehicle"]["earned"] == 15  # kind 10 + make 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ride_score.py -v`
Expected: FAIL — `ModuleNotFoundError: hitch.blueprints.utils.ride_score`.

- [ ] **Step 3: Write the Python mirror**

Create `hitch/blueprints/utils/ride_score.py`:

```python
"""Python mirror of hitch/static/ride_score.js. Reads the SAME canonical weights
file so the two can never disagree on point values. Used by later phases to compute
per-user aggregates from stored ride content."""

import json
import pathlib

# hitch/blueprints/utils/ride_score.py -> parents[2] == hitch/ ; weights live in hitch/static/.
_WEIGHTS_PATH = pathlib.Path(__file__).resolve().parents[2] / "static" / "ride_score_weights.json"
WEIGHTS = json.loads(_WEIGHTS_PATH.read_text())
PASSENGER_KINDS = set(WEIGHTS["passenger_kinds"])


def _is_filled(field: str, value) -> bool:
    # Mirrors isFilled() in ride_score.js — commercial is tri-state (True/False both count).
    if field == "commercial":
        return value is True or value is False
    if isinstance(value, (list, tuple)):
        return len(value) > 0
    if field == "driver_age":
        return value is not None and str(value).strip() != ""
    return isinstance(value, str) and value.strip() != ""


def _score_group(fields: dict, weight_map: dict):
    earned = 0
    max_pts = 0
    missing = []
    for field, pts in weight_map.items():
        max_pts += pts
        if _is_filled(field, fields.get(field)):
            earned += pts
        else:
            missing.append({"field": field, "pts": pts})
    return earned, max_pts, missing


def score_fields(fields: dict) -> dict:
    fields = fields or {}
    d_earned, d_max, d_missing = _score_group(fields, WEIGHTS["driver"])
    d_pct = round(d_earned / d_max * 100) if d_max else 0

    b_earned, b_max, b_missing = _score_group(fields, WEIGHTS["vehicle_base"])
    bonus_eligible = fields.get("vehicle_kind") in PASSENGER_KINDS
    v_earned, v_max, v_missing = b_earned, b_max, list(b_missing)
    if bonus_eligible:
        x_earned, x_max, x_missing = _score_group(fields, WEIGHTS["vehicle_bonus"])
        v_earned += x_earned
        v_max += x_max
        v_missing.extend(x_missing)
    v_missing.sort(key=lambda m: m["pts"], reverse=True)
    d_missing.sort(key=lambda m: m["pts"], reverse=True)
    v_pct = round(v_earned / v_max * 100) if v_max else 0

    return {
        "driver": {"earned": d_earned, "max": d_max, "pct": d_pct, "missing": d_missing},
        "vehicle": {"earned": v_earned, "max": v_max, "pct": v_pct, "missing": v_missing, "bonus_eligible": bonus_eligible},
        "total": d_earned + v_earned,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ride_score.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add hitch/blueprints/utils/ride_score.py tests/test_ride_score.py
git commit -m "feat(score): python scoring mirror reading the shared weights"
```

---

### Task 3: `commercial` in the transport model + record builder

**Files:**
- Modify: `hitch/blueprints/utils/hitchhiking_data_standard_pydantic_model.py:92-97`
- Modify: `hitch/blueprints/publish_ride.py:153-164`
- Test: `tests/test_commercial_field.py`

**Interfaces:**
- Consumes: `create_record_from_custom_object(custom_object, source, license)` reads `custom_object["vehicle_commercial"]` as `True`/`False`/`None`.
- Produces: `HitchhikingRecord.mode_of_transportation.commercial` (`Optional[bool]`), serialized into the `mode_of_transportation` JSON.

- [ ] **Step 1: Write the failing test**

Create `tests/test_commercial_field.py`:

```python
from hitch.blueprints.publish_ride import create_record_from_custom_object


def _base_object(**extra):
    obj = {
        "rate": 4, "wait": 10, "signal": [], "comment": None,
        "pickup_lat": 48.2, "pickup_lon": 16.37,
        "destination_lat": 48.5, "destination_lon": 16.9,
        "datetime_ride": "2026-07-02T14:00", "arrival_datetime": "2026-07-02T14:41",
        "vehicle_kind": "van",
    }
    obj.update(extra)
    return obj


def test_commercial_true_serialized_into_transport():
    rec = create_record_from_custom_object(_base_object(vehicle_commercial=True), "hitchmap", "CC0")
    assert rec.mode_of_transportation.commercial is True


def test_commercial_false_serialized_into_transport():
    rec = create_record_from_custom_object(_base_object(vehicle_commercial=False), "hitchmap", "CC0")
    assert rec.mode_of_transportation.commercial is False


def test_commercial_absent_is_none():
    rec = create_record_from_custom_object(_base_object(), "hitchmap", "CC0")
    assert rec.mode_of_transportation.commercial is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_commercial_field.py -v`
Expected: FAIL — `TypeError`/`ValidationError` (no `commercial` on `ModeOfTranportation`).

- [ ] **Step 3: Add the pydantic field**

In `hitch/blueprints/utils/hitchhiking_data_standard_pydantic_model.py`, modify `ModeOfTranportation` (currently lines 92-97):

```python
class ModeOfTranportation(BaseModel, use_enum_values=True):
    kind: KindEnum = Field(...)
    make: Optional[str] = None
    model: Optional[str] = None
    # Explicit "the driver was operating commercially" flag. Tri-state: None = unanswered,
    # because even a truck/bus can be a private conversion (a schoolie) so it is never
    # inferred from `kind` — only ever the value the user set.
    commercial: Optional[bool] = None
    license_plate_country: Optional[str] = None  # ISO 3166-1 alpha-2
    license_plate_identifier: Optional[str] = None
```

- [ ] **Step 4: Thread it through the record builder**

In `hitch/blueprints/publish_ride.py`, modify the `ModeOfTranportation(...)` construction (currently lines 159-164) to pass `commercial`:

```python
    if vehicle_kind in ALLOWED_VEHICLE_KINDS:
        country = (custom_object.get("vehicle_license_plate_country") or "").strip().upper() or None
        # commercial is already a bool (or None) by the time it reaches here; the /ride
        # handler parses the raw form string. Pass through unchanged.
        commercial = custom_object.get("vehicle_commercial")
        commercial = commercial if commercial in (True, False) else None
        mode_of_transportation = ModeOfTranportation(
            kind=vehicle_kind,
            make=(custom_object.get("vehicle_make") or "").strip() or None,
            model=(custom_object.get("vehicle_model") or "").strip() or None,
            commercial=commercial,
            license_plate_country=country,
            license_plate_identifier=(custom_object.get("vehicle_license_plate_identifier") or "").strip() or None,
        )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_commercial_field.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add hitch/blueprints/utils/hitchhiking_data_standard_pydantic_model.py hitch/blueprints/publish_ride.py tests/test_commercial_field.py
git commit -m "feat(ride): add commercial flag to mode_of_transportation JSON"
```

---

### Task 4: Parse `vehicle_commercial` on the `/ride` route (POST + GET)

**Files:**
- Modify: `hitch/blueprints/main.py` (POST vehicle-validation block ~592-600; GET edit-prefill block ~417-452)
- Test: `tests/test_commercial_route.py`

**Interfaces:**
- Consumes: form field `vehicle_commercial` as `"true"` / `"false"` / `""`.
- Produces: `data["vehicle_commercial"]` set to `True` / `False` / `None` before `create_record_from_custom_object` (Task 3) runs; GET edit `ride_data["vehicle_commercial"]` read back from stored JSON.

- [ ] **Step 1: Write the failing test**

Create `tests/test_commercial_route.py`:

```python
import hitch.blueprints.main as main


class _CapturePoster:
    """Captures the record so the test can assert commercial round-trips through /ride."""
    captured = {}

    def post(self, ride_record, tags=None, d_tag=None):
        _CapturePoster.captured["record"] = ride_record
        return "dtag123"

    def close(self):
        pass


def _post(client, **extra):
    data = {
        "rate": "4", "wait": "10", "signal": "thumb", "comment": "",
        "pickup_lat": "48.2", "pickup_lon": "16.37",
        "destination_lat": "48.5", "destination_lon": "16.9",
        "datetime_ride": "2026-07-02T14:00", "arrival_datetime": "2026-07-02T14:41",
        "vehicle_kind": "van",
    }
    data.update(extra)
    return client.post("/ride", data=data, headers={"X-Requested-With": "inride"})


def test_commercial_true_posts_through(client, monkeypatch):
    monkeypatch.setattr(main, "HitchhikingDataStandardToNostrPoster", _CapturePoster)
    resp = _post(client, vehicle_commercial="true")
    assert resp.status_code == 200
    assert _CapturePoster.captured["record"].mode_of_transportation.commercial is True


def test_commercial_false_posts_through(client, monkeypatch):
    monkeypatch.setattr(main, "HitchhikingDataStandardToNostrPoster", _CapturePoster)
    resp = _post(client, vehicle_commercial="false")
    assert resp.status_code == 200
    assert _CapturePoster.captured["record"].mode_of_transportation.commercial is False


def test_commercial_absent_is_none(client, monkeypatch):
    monkeypatch.setattr(main, "HitchhikingDataStandardToNostrPoster", _CapturePoster)
    resp = _post(client)
    assert resp.status_code == 200
    assert _CapturePoster.captured["record"].mode_of_transportation.commercial is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_commercial_route.py -v`
Expected: FAIL — `commercial` is `None` even when `vehicle_commercial="true"` (not yet parsed).

- [ ] **Step 3: Parse the POST field**

In `hitch/blueprints/main.py`, inside the vehicle-validation block (just after the `vehicle_make`/`vehicle_model`/`vehicle_license_plate_identifier` loop, ~line 600), add:

```python
        # commercial toggle: tri-state from the form. "true"/"false" -> bool; anything
        # else (unanswered) -> None. Never inferred from kind (see design §2).
        commercial_raw = (data.get("vehicle_commercial") or "").strip().lower()
        assert commercial_raw in ("", "true", "false"), f"Invalid commercial value: {commercial_raw}"
        data["vehicle_commercial"] = True if commercial_raw == "true" else (False if commercial_raw == "false" else None)
```

- [ ] **Step 4: Read it back on GET edit-prefill**

In `hitch/blueprints/main.py`, in the GET edit-prefill `ride_data` dict (after `"vehicle_license_plate_identifier": "",` at line 421) add the key:

```python
                    "vehicle_commercial": "",
```

and in the `mot` extraction block (after line 452, `ride_data["vehicle_license_plate_identifier"] = ...`) add:

```python
                    # Round-trip the stored tri-state back to the form's string values.
                    _c = mot.get("commercial")
                    ride_data["vehicle_commercial"] = "true" if _c is True else ("false" if _c is False else "")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_commercial_route.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Run the full backend suite for regressions**

Run: `python -m pytest tests/test_inride_submit.py tests/test_inride_outbox.py tests/test_commercial_field.py tests/test_commercial_route.py -q`
Expected: all pass (the pre-existing live-relay `test_integration` is not in this set).

- [ ] **Step 7: Commit**

```bash
git add hitch/blueprints/main.py tests/test_commercial_route.py
git commit -m "feat(ride): parse vehicle_commercial on /ride POST and edit-prefill"
```

---

### Task 5: Extract & extend the in-ride Finish body builder for demographics

**Files:**
- Create: `hitch/static/ride_submit.js`
- Modify: `hitch/static/inride.js:93-120` (remove local `isoLocal` + `buildFinishBody`; delegate to `RideSubmit`)
- Modify: `hitch/templates/map.html:46` (load new scripts before `inride.js`)
- Test: `tests/ride_submit.test.js`

**Interfaces:**
- Consumes: a journey object `j` with `{pickup:{lat,lon}, gotRideMs, finalWaitMs, details}` where `details` may carry any of the canonical field names plus `rating`, `signal`, `comment`, `commercial`.
- Produces: `RideSubmit.buildFinishBody(j, dest, finishMs, id) -> object` (the `/ride` POST body, now including all demographic fields) and `RideSubmit.isoLocal(ms) -> "YYYY-MM-DDTHH:mm"`. Browser: `window.RideSubmit`; Node: `module.exports`.

- [ ] **Step 1: Write the failing test**

Create `tests/ride_submit.test.js`:

```js
const test = require("node:test");
const assert = require("node:assert");
const RideSubmit = require("../hitch/static/ride_submit.js");

const J = {
  pickup: { lat: 48.2, lon: 16.37 },
  gotRideMs: new Date(2026, 6, 2, 14, 0).getTime(),
  finalWaitMs: 12 * 60000,
  details: {
    rating: 4,
    signal: ["thumb"],
    comment: "nice",
    vehicle_kind: "van",
    commercial: false,
    driver_reason_to_pick_up: ["curiosity"],
    driver_gender: "female",
    driver_age: 34,
    driver_origin_country: "DE",
    driver_languages: ["deu", "eng"],
    vehicle_make: "Toyota",
    vehicle_model: "Hiace",
    vehicle_license_plate_country: "DE",
  },
};

test("buildFinishBody carries every demographic field", () => {
  const dest = { lat: 48.5, lon: 16.9 };
  const finishMs = new Date(2026, 6, 2, 14, 41).getTime();
  const body = RideSubmit.buildFinishBody(J, dest, finishMs, "abc-123");

  assert.strictEqual(body.rate, "4");
  assert.strictEqual(body.wait, "12");
  assert.strictEqual(body.signal, "thumb");
  assert.strictEqual(body.datetime_ride, "2026-07-02T14:00");
  assert.strictEqual(body.arrival_datetime, "2026-07-02T14:41");
  assert.strictEqual(body.client_d_tag, "abc-123");
  assert.strictEqual(body.driver_reason_to_pick_up, "curiosity");
  assert.strictEqual(body.driver_gender, "female");
  assert.strictEqual(body.driver_age, "34");
  assert.strictEqual(body.driver_origin_country, "DE");
  assert.strictEqual(body.driver_languages, "deu,eng");
  assert.strictEqual(body.vehicle_make, "Toyota");
  assert.strictEqual(body.vehicle_model, "Hiace");
  assert.strictEqual(body.vehicle_license_plate_country, "DE");
  assert.strictEqual(body.vehicle_commercial, "false");
});

test("absent demographic fields serialize to empty strings", () => {
  const body = RideSubmit.buildFinishBody(
    { pickup: { lat: 1, lon: 2 }, gotRideMs: Date.now(), finalWaitMs: 0, details: { rating: 3 } },
    { lat: 3, lon: 4 }, Date.now(), "id1"
  );
  assert.strictEqual(body.driver_gender, "");
  assert.strictEqual(body.driver_languages, "");
  assert.strictEqual(body.vehicle_commercial, "");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test tests/ride_submit.test.js`
Expected: FAIL — `Cannot find module '../hitch/static/ride_submit.js'`.

- [ ] **Step 3: Create the extracted, extended module**

Create `hitch/static/ride_submit.js`:

```js
// Pure /ride POST-body builder for the in-ride Finish flow. Extracted from inride.js
// so it is unit-testable (Node) and reusable by later enrichment phases. Browser:
// window.RideSubmit; Node: module.exports.
(function (root, factory) {
  const mod = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = mod;
  else root.RideSubmit = mod;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // "YYYY-MM-DDTHH:mm" from LOCAL date components — NOT toISOString() (UTC), which
  // would silently offset times by the user's UTC offset.
  function isoLocal(ms) {
    const d = new Date(ms);
    const pad = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }

  // Build the /ride form body from a journey + destination. client_d_tag pins the Nostr
  // d_tag so outbox retries replace rather than duplicate. finishMs is captured at the
  // START of journeyFlow.finish() so GPS/manual-pin delay doesn't inflate arrival time.
  function buildFinishBody(j, dest, finishMs, id) {
    const d = j.details || {};
    const csv = (v) => (Array.isArray(v) ? v.join(",") : (v || ""));
    return {
      rate: String(d.rating || ""),
      wait: String(Math.round((j.finalWaitMs || 0) / 60000)),
      signal: csv(d.signal),
      comment: d.comment || "",
      vehicle_kind: d.vehicle_kind || "",
      // Demographic carry-through (Phase 2 UI populates these onto j.details).
      driver_reason_to_pick_up: csv(d.driver_reason_to_pick_up),
      driver_gender: d.driver_gender || "",
      driver_age: (d.driver_age === 0 || d.driver_age) ? String(d.driver_age) : "",
      driver_origin_country: d.driver_origin_country || "",
      driver_languages: csv(d.driver_languages),
      vehicle_make: d.vehicle_make || "",
      vehicle_model: d.vehicle_model || "",
      vehicle_license_plate_country: d.vehicle_license_plate_country || "",
      // Tri-state -> the form's string values; "" means unanswered.
      vehicle_commercial: d.commercial === true ? "true" : (d.commercial === false ? "false" : ""),
      pickup_lat: j.pickup.lat, pickup_lon: j.pickup.lon,
      destination_lat: dest.lat, destination_lon: dest.lon,
      datetime_ride: isoLocal(j.gotRideMs),
      arrival_datetime: isoLocal(finishMs),
      client_d_tag: id,
    };
  }

  return { isoLocal, buildFinishBody };
});
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test tests/ride_submit.test.js`
Expected: PASS (2 tests).

- [ ] **Step 5: Delete the now-duplicated functions from inride.js and delegate**

In `hitch/static/inride.js`, remove the local `isoLocal` (lines 93-99) and `buildFinishBody` (lines 101-120) definitions, replacing both with a delegation shim near the top of the IIFE (right after `"use strict";` block's constants):

```js
  // isoLocal + buildFinishBody live in ride_submit.js (loaded before this file) so they
  // can be unit-tested outside the DOM. Alias them locally to keep call sites unchanged.
  const isoLocal = window.RideSubmit.isoLocal;
  const buildFinishBody = window.RideSubmit.buildFinishBody;
```

- [ ] **Step 6: Verify inride.js still parses and has no leftover definitions**

Run: `node --check hitch/static/inride.js && grep -nc "function buildFinishBody\|function isoLocal" hitch/static/inride.js`
Expected: `inride.js` parses OK; grep prints `0` (no duplicate definitions remain).

- [ ] **Step 7: Load the new modules in the template**

In `hitch/templates/map.html`, before line 46 (`<script src="{{ asset_url('/static/inride.js') }}"></script>`), add:

```html
<script src="{{ asset_url('/static/ride_score.js') }}"></script>
<script src="{{ asset_url('/static/ride_submit.js') }}"></script>
```

- [ ] **Step 8: Commit**

```bash
git add hitch/static/ride_submit.js hitch/static/inride.js hitch/templates/map.html tests/ride_submit.test.js
git commit -m "refactor(inride): extract ride_submit.js and carry demographics into Finish body"
```

---

## Self-Review

- **Spec coverage (Phase 1 items):** single-source weights (Task 1 JSON + Tasks 1/2 readers) ✓; `computeScores` JS (Task 1) ✓; Python mirror + parity via shared file (Task 2) ✓; `commercial` on the transport model, never inferred (Tasks 3–4) ✓; extend `j.details`/`buildFinishBody` carry-through (Task 5) ✓; PASSENGER_KINDS gating make/model (Tasks 1–2) ✓; plate identifier never scored (weights omit it) ✓. Deferred to later phases by design: during-ride meters/sheet (Phase 2), completion enrich (Phase 3), historic-form restyle (Phase 4), per-user aggregate/level/streak + "Your rides"/queue (Phase 5). `score_fields` (Task 2) is the foundation Phase 5 consumes.
- **Placeholder scan:** none — every step has concrete code/commands.
- **Type consistency:** field names identical across JSON, `computeScores`, `score_fields`, `buildFinishBody`, and the `/ride` handler; `commercial` (JSON key) ↔ `vehicle_commercial` (form field) mapping is explicit in Tasks 3–5; return shapes (`driver`/`vehicle`/`total`, `bonusEligible`/`bonus_eligible`) are consistent within each language.

## Phasing note

Phases 2–5 (UI meters + in-ride Save, completion enrich sheet, historic-form restyle, post-hitching "Your rides"/queue + per-user score) each get their own plan once Phase 1 lands, since each produces working, testable software on its own.
