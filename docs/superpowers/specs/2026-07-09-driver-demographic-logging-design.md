# Driver-demographic logging experience — design

- **Date:** 2026-07-09
- **Status:** Approved (design); implementation phased
- **Related:** Issue #100 flow (in-ride tracker + outbox), Issue #101 (feature request)

## Goal

Obtain high-quality **sociologic data** about who picks up hitchhikers, by making
high-quality logs a natural part of the flow rather than a chore bolted on afterward.
The mechanism is a two-part **completeness score** plus nudges at three moments —
**during the ride**, **immediately on completion**, and **post-hitching**.

## Non-goals & hard constraints

- **No structural database changes.** Vehicle detail lives in the `mode_of_transportation`
  **JSON column** (`RideEvent`, `models.py:135`) and driver detail in ride-event JSON
  content; every new field added here is a JSON key or a derived value, never a new column.
  Scores are always **computed**, never stored.
- No new gamification currency beyond points/level/streak; no leaderboards, no rewards store (YAGNI).
- `license_plate_identifier` remains capturable but is **never scored, nudged, or incentivized** — it is PII, not sociologic data.

## 1. Scoring model

Two **independent** meters per ride, produced by one pure function from the ride's field set.
A rider who logs *why* a trucker stopped but not the model still earns a full Driver score.

### Driver score (max 60)

| Field | Pts | Rationale |
|---|---|---|
| `driver_reason_to_pick_up` | 15 | Motivation — the closest thing to a "why hitchhiking works" variable |
| `driver_gender` | 15 | Canonical demographic; strong explanatory power |
| `driver_age` (approx.) | 10 | Canonical demographic; a rough estimate is fine (see §3 copy) |
| `driver_origin_country` | 10 | Culture/nationality; doubly relevant for cross-border rides |
| `driver_languages` | 10 | Cultural / human-capital signal |

### Vehicle score (base 40; + up to 10 make/model bonus for passenger vehicles)

| Field | Pts | Counts as | Rationale |
|---|---|---|---|
| `vehicle_license_plate_country` | 20 | base | Mobility/origin — corroborates driver origin and reveals cross-border movement; the single strongest vehicle-side signal |
| `vehicle_kind` | 10 | base | Distinguishes structurally different driver populations |
| `commercial` (new JSON key) | 10 | base | Commercial vs private is a high-value population split; see §2 and §6 |
| `vehicle_make` | +5 | **bonus (passenger only)** | Rough socioeconomic-class proxy (noisy) |
| `vehicle_model` | +5 | **bonus (passenger only)** | Marginal extra over make |
| ~~`vehicle_license_plate_identifier`~~ | — | excluded | PII |

**Base scale = 100** (Driver 60 + Vehicle base 40). `make`/`model` are **bonus** on top of the
base, and only meaningful for passenger vehicles — a rider rarely knows (or cares about) the
make/model of a truck, bus, train, or ferry. They are offered and counted **only** when
`kind ∈ PASSENGER_KINDS = {car, van, camper, taxi, motorbike, scooter}` (tunable in one place);
for other kinds the make/model inputs are hidden and un-nudged. A fully-detailed passenger ride
can therefore reach **110**. Bonus points still add to the per-user total (§ below); the per-ride
meters read 100% at base, with make/model shown as an optional "+5" beyond.

Field weights: plate country 20; motivation, gender at 15 (Driver table); age, origin, languages,
vehicle kind, commercial at 10; make, model at 5 (bonus). Plate country is deliberately the
top-weighted single field — origin/mobility is treated as the key vehicle-side signal.

### Per-user aggregate (logged-in only)

- **Points:** Σ (driver + vehicle earned, including make/model bonus) across the user's rides.
- **Level:** tunable threshold curve. Initial thresholds: `[0, 100, 250, 500, 900, 1400, 2000]`
  (Lvl 1…7); a user's level is the highest threshold their cumulative points meet or exceed.
- **Streak:** count of consecutive **most-recent** rides (by ride datetime, descending) whose
  **Driver meter is 100%** (all 60 pts). The first ride below 100% ends the streak. Threshold
  (Driver = 100%) is tunable in one place.
- **Anonymous rides** show per-ride meters but do **not** accrue to any user score (no identity to attribute to).

## 2. Data model & carry-through (no structural DB changes)

- Add optional `commercial: Optional[bool]` to `ModeOfTranportation`
  (`hitchhiking_data_standard_pydantic_model.py:92`). It serializes into the existing
  `mode_of_transportation` JSON — **app-level change only**. Because even nominally-commercial
  kinds can be private conversions (a `bus` schoolie, a converted box `truck`), `commercial`
  is **never inferred from `kind`** — it is only ever the explicit value the user set.
- The backend `/ride` handler already parses every driver/vehicle field
  (`main.py:418–452`). The gap is the **in-ride submit path**: `j.details`
  (`inride.js`, `journeyFlow.gotRide`) and `buildFinishBody()` (`inride.js:106`) today carry
  only `{rating, vehicle_kind, signal, comment}` and **drop** the rest. Extend both to carry
  all Driver + Vehicle fields, including `commercial`.
- **Weights are single-sourced.** One canonical definition (a small JSON module) is consumed
  by the frontend `computeScores` and by the Python per-user aggregate. A parity test asserts
  the two never drift.

## 3. Shared demographic component

One reusable Driver / Vehicle block, rendered in **three hosts** (in-ride sheet, completion
enrich sheet, restyled `/ride` form) so behavior and scoring are defined once:

- **Driver block:** reason-to-pick-up (multi-select chips), gender (chips), age (stepper),
  origin country (searchable picker), languages (multi-select). Live **Driver meter**.
  The age field is framed as **approximate** so riders don't feel they must be exact — label
  **"Approx. driver age"** with helper text *"A rough guess is fine."* The stored value stays
  the numeric estimate; the field still earns its 10 points whether exact or estimated.
- **Vehicle block:** vehicle kind (chips + expand, §6), **Commercial / private?** toggle,
  plate country, and — **only when the kind is a passenger vehicle** (`PASSENGER_KINDS`) —
  make and model as an optional "+5 bonus" pair. Non-passenger kinds hide make/model entirely.
  Live **Vehicle meter** (base 40; bonus renders beyond 100%).
- Meters update on every field change and show the top missing high-value fields as
  "+N" affordances.

## 4. Nudge surfaces

### During the ride
The in-ride bar surfaces the two mini-meters (`Driver ▓ 40%  Vehicle ▓ 20%`) + an
"Add details" affordance. It opens the shared component as a bottom sheet. **Save writes the
fields onto `j.details`, persists the journey, and returns to the in-ride bar — it never
publishes** (the ride isn't over). This replaces today's "＋ Add driver / vehicle details"
link, which redirects to `/ride` and would prematurely submit a completed ride.

### Immediately on completion
Finish **publishes/enqueues first** (preserving the offline-safe "a ride is never lost"
guarantee), then a **non-blocking** enrich sheet appears showing the two meters and the top
missing fields. "Add details" opens the shared component; "Skip" dismisses. Saving **edits and
re-publishes the same `d_tag`** through the existing outbox — idempotent (kind 36820 replaceable
event is *replaced*, not duplicated) and offline-safe.

### Post-hitching (both surfaces)
- **"Your rides"** (logged-in): a header with per-user **score / level / streak**, then the
  user's rides each showing their two meters; tapping an incomplete ride opens the enrich
  component (edit → re-publish same `d_tag`).
- **"Needs enrichment" queue:** a filtered entry point listing only incomplete rides, as a
  fast on-ramp into the enrichment component.

## 5. Historic `/ride` form

Restyle the clunky demographic section (`ride_form.html`) into the shared component — Driver /
Vehicle blocks with live meters, chip/stepper inputs, and the commercial toggle. The standalone
**"Log a past ride"** entry keeps a **Submit** button (publishes a full ride); the **mid-ride**
host uses **Save** (writes back to the journey). Same component, different terminal action set
by the host.

## 6. Vehicle-kind selector: expand to non-standard vehicles

"Who picked you up?" currently offers only 3 of the 14 `KindEnum` values (car / truck / van;
`inride.js:839`). The shared vehicle selector keeps the three common chips inline plus a
**"＋ More"** chip that expands the full remaining list from the single existing source
(`ALLOWED_VEHICLE_KINDS` / `VEHICLE_KIND_EMOJIS`, `main.py:47`): bus 🚌, motorbike 🏍, scooter 🛵,
taxi 🚕, horse-cart 🐎, train 🚆, camper 🏕, tractor 🚜, plane ✈️, ferry ⛴, boat ⛵. Selecting a
non-standard kind selects it (single-select) and collapses the overflow, showing the chosen chip.
No new vocabulary — the values are the same `KindEnum` used everywhere, so nothing new to persist
or coordinate with the data standard.

## 7. Error handling, edge cases, privacy

- **Offline enrichment** rides the existing outbox; same-`d_tag` edits replace rather than duplicate.
- **Ambiguous kinds** are never auto-classified; `commercial` is only ever user-set.
- **PII:** `license_plate_identifier` stays capturable but is excluded from scoring and never
  surfaced in a nudge.
- **Anonymous users:** per-ride meters render, but no per-user score/level/streak.

## 8. Testing

- **Frontend:** `computeScores` per tier; independent meters; missing-field ordering; commercial
  toggle contributes points; vehicle-kind expand selects non-standard kinds.
- **Backend:** per-user aggregate, level thresholds, streak reset; demographic round-trip through
  `/ride` (all fields persist); edit re-publish carries new fields under the same `d_tag`;
  `commercial` survives the JSON round-trip; weight-parity test (frontend vs backend weights).

## 9. Implementation phasing (one spec, phased plan)

1. **Scoring foundation + carry-through** — single-source weights, `computeScores`, extend
   `j.details` + `buildFinishBody`, add `commercial` to the pydantic model. Unblocks everything.
2. **In-ride Save + during-ride meters** — shared component, the save-vs-submit mechanic,
   vehicle-kind expand, mini-meters in the in-ride bar.
3. **Completion enrich sheet** — publish-first, then non-blocking enrich → edit re-publish.
4. **Historic form restyle** — embed the shared component in `/ride`.
5. **Post-hitching** — "Your rides" + "needs enrichment" queue + per-user score/level/streak
   (backend aggregate endpoint + UI).

## 10. Locked decisions

- Two meters, base 100 = Driver 60 + Vehicle base 40 (plate country 20, kind 10, commercial 10).
  Driver: reason 15, gender 15, age 10, origin 10, languages 10. `make`/`model` are +5/+5 bonus,
  passenger-kinds only → max 110. Plate identifier excluded (PII). Age framed as approximate.
- Per-user score + per-ride meter; streak = consecutive recent rides at Driver 100%.
- Commercial handled via an explicit in-JSON `commercial` toggle, always offered, never inferred.
- Completion nudge publishes first, then enriches via same-`d_tag` edit.
- Historic form restyled with the shared component; post-hitching uses both "Your rides" and a queue.
- Vehicle-kind selector expands to the full existing `KindEnum` list under "Who picked you up?".
