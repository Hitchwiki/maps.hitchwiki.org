# In-Ride Hitching Tracker — Design

**Date:** 2026-07-02
**Status:** Approved design, pending spec review
**Mockups:** `scratchpad/inride-mockups.html` (throwaway visual reference)

## Goal

Let a hitchhiker log a real ride with **near-zero manual data entry**, capturing the
data that is normally tedious or forgotten — especially **wait time** and **ride
start/stop times** — automatically from timestamps and GPS as the journey happens.

The user drives a small state machine with big tappable buttons ("Start Hitching",
"Give Up", "Got a Ride!", "Finish Ride"); the app derives pickup/destination
coordinates, waiting duration, departure/arrival times, and distance from those taps.

## Non-goals (YAGNI)

- No continuous route/breadcrumb tracking or background geolocation while the app is closed.
- No editing of a journey's pickup after it has started (cancel & restart instead).
- No new server-side ride schema — reuse the existing ride submission path and Nostr event shape.
- No offline submission queue beyond "keep local state and let the user retry".

## Approach

A self-contained front-end state machine layered on top of the existing map, persisted
in `localStorage` so it survives reloads and long waits. It reuses existing building
blocks: the current-location marker, the location-selection/add-spot flow (for "Add
Spot" and manual-pin fallbacks), and the existing ride submission backend.

**New module:** `hitch/static/inride.js`, loaded after `map.js` in `map.html`. It owns
the journey state, the persistent docked UI, the dialogs, and submission. It calls a
small number of functions/objects exposed by `map.js` (the `map` instance, the location
marker, `setupLocationSelection`, `findNearbySpotMarker`). Rationale: `map.js` is already
~3000 lines; a focused module keeps this feature readable and independently testable.

*Alternatives considered:* (a) put everything in `map.js` — rejected, file is already
large; (b) a server-tracked journey (DB row per journey) — rejected as over-engineered:
the journey is inherently a single-device, single-user, transient thing, and only the
**final** ride needs to be published.

## State machine

```
                 ┌─────────────────────────── Add Spot (existing flow) ──────────┐
                 │                                                                 │
  idle ──long-press / bubble-tap──▶ choose-action ──Start Hitching──▶ waiting     │
                 │                                       (login gate)     │        │
                 └──tap outside: cancel──────────────────────────────────┘        │
                                                                                   ▼
   waiting ──Give Up──▶ Add-Spot ride form (prefilled wait + comment) ──save──▶ idle
   waiting ──Got a Ride!──▶ ride-details sheet ──save──▶ in-ride
   in-ride ──Finish Ride──▶ capture destination (auto-GPS / manual) ──submit──▶ whats-next
   whats-next ──Next Ride──▶ waiting  (drop-off becomes new pickup, fresh timestamps)
   whats-next ──End Hitch──▶ idle
```

Persisted states: `idle` (nothing stored), `waiting`, `in-ride`. `choose-action`,
`whats-next`, and the details sheet are transient dialogs (not persisted; if the app
closes while one is open, we resume the last persisted state — `waiting` or `in-ride`).

## Entry points → choose-action dialog

Two ways to open the **choose-action** dialog at a location:

1. **Long-press** a map location (currently goes straight to add-spot). This now opens
   the choose-action dialog first.
2. **Tap the current-location bubble** (`locationMarker`). Requires the user to have
   tapped the GPS button first (that is what creates the bubble). The bubble becomes
   interactive and opens the dialog at its position.

**Dialog (Variant A — stacked, dark scrim):**
- Title: "This spot"
- **Start Hitching** — green primary (`--green #1a9850`)
- **Add Spot** — secondary ghost/blue-outline
- Tap anywhere outside the card (on the scrim) cancels and returns to `idle`.

"Add Spot" preserves the current behavior exactly (`setupLocationSelection('select-pickup',
… isNewSpot)` with its snap-to-nearby-spot and confirm card).

## Login gate

"Start Hitching" requires a logged-in user (submitting a tracked ride implies ownership).

- If anonymous: stash the intended pickup `{lat, lon}` in `localStorage`
  (`inride.pendingStart`), then redirect to `/login?next=/` (the map). On return, if
  `pendingStart` exists and the user is now logged in, go **straight to `waiting`** at
  the stashed location (they already chose Start Hitching) and clear `pendingStart`. If
  they return still anonymous (abandoned login), discard `pendingStart` and do nothing.
- "Add Spot" remains available anonymously (unchanged).

Whether the app knows "logged in" client-side: `map.html` already renders an
`is_logged_in` flag into the page (used elsewhere). `inride.js` reads that flag.

## Waiting state

- **Journey start timestamp** recorded when `waiting` begins (this is `t_waitStart`).
- Pickup coordinates = the chosen location. For "Start Hitching", if we have a fresh GPS
  fix (bubble tap) we use it; otherwise we prompt GPS permission, and on denial the user
  drops the pin manually (reusing the location-selection pin UI).
- **Persistent docked bar** (`position:fixed`, above zoom controls), restored on reload:
  - **Give Up** — big red (`--red #d73027`)
  - **Got a Ride!** — big green (`--green`)
- **Status chip** above the bar shows a live `Waiting · HH:MM:SS` timer (ticks each
  second; the authoritative value is always `now − t_waitStart`, so reloads are exact).

### Give Up

Opens the **existing Add-Spot → ride form** flow, pre-filled with:
- `wait` = `round((t_giveUp − t_waitStart) / 60000)` minutes
- an empty comment field for the user to fill
- pickup = the waiting location

Rating stays **required** (unchanged form rule — the user rates the spot). On save, the
form submits through the normal path; the journey state is cleared to `idle`.

Mechanism: reuse the existing `sessionStorage.rideFormData` prefill that
`selectLocation()` already uses, then navigate to `/ride`.

## Got a Ride! → ride-details sheet

Tapping "Got a Ride!" records `t_gotRide` (= departure time, and the end of waiting) and
opens a **slim bottom sheet** (not the full form):
- Star **rating** (required)
- **Vehicle kind** chips (Car/Truck/Van/…), default Car
- **Signal** chips (Thumb/Sign/Asking)
- **Comment** (optional)
- **"Start ride"** primary button → transitions to `in-ride`
- **"＋ Add driver / vehicle details"** link → opens the full ride form for power users
  (their in-sheet selections carried over via the existing sessionStorage prefill).

The captured details + `t_gotRide` + pickup + wait duration are stored in the `in-ride`
localStorage record; **submission is deferred** to Finish Ride (when the destination is known).

## In-ride state

- **Persistent docked bar**, restored on reload:
  - **Finish Ride** — big orange (`--orange #ff6b35`)
- **Status chip**: live `In a ride · HH:MM:SS` timer from `t_gotRide`.

### Finish Ride

1. Record `t_finish` (= arrival time).
2. **Capture destination:** request a GPS fix; on success that is the destination. On
   denial/failure, drop the pin manually (location-selection UI).
3. **Submit the ride** through the existing ride backend with the assembled payload
   (see Data Mapping). Show progress on the button (Nostr publish is ~5s per CLAUDE.md).
   - On success → **What's next?** dialog.
   - On failure → keep `in-ride` state, show an error, allow retry; offer "open full
     form" as an escape hatch (hands off via sessionStorage prefill).

## What's next? (post-ride)

Transient dialog after a successful submit:
- Title: "What's next?"
- **Next Ride** — green: the drop-off location becomes the **new pickup**, a fresh
  `t_waitStart = now` is set, and state returns to `waiting` (new leg, new timestamps).
- **End Hitch** — grey: clear journey state → `idle`.

This makes multi-leg trips effortless without re-selecting a location.

## Data mapping (zero-typing capture)

Reusing the existing ride/Nostr shape (`stops[0]` = pickup, `stops[-1]` = destination):

| Ride field | Source |
|---|---|
| pickup lat/lon (`stops[0].location`) | journey start location |
| `waiting_duration` (`PT<n>M`) | `t_gotRide − t_waitStart`, rounded to minutes |
| `departure_time` (`stops[0]`) | `t_gotRide` (ISO 8601) |
| destination lat/lon (`stops[-1]`) | GPS fix at Finish Ride (manual fallback) |
| `arrival_time` (`stops[-1]`) | `t_finish` (ISO 8601) |
| distance | derived pickup → destination (as today) |
| `rating`, vehicle, signal, comment | ride-details sheet |

Only manual inputs in the whole happy path: rating + optional chips at "Got a Ride!", and
a comment at "Give Up".

## localStorage schema

Key `inride.journey`:
```json
{
  "state": "waiting | in-ride",
  "pickup": { "lat": 48.20, "lon": 16.37 },
  "waitStartMs": 1751459200000,
  "gotRideMs": null,
  "details": null,            // rating/vehicle/signal/comment once Got-a-Ride is saved
  "legIndex": 0               // increments on Next Ride (informational)
}
```
Key `inride.pendingStart`: `{ "lat": …, "lon": … }` (only across the login redirect).

Written on every transition; read once on page load to rehydrate the docked UI + timer.

## Resume on load

On map init, `inride.js` reads `inride.journey`:
- `waiting` → render the Give Up / Got a Ride bar + waiting timer; re-draw pickup pin.
- `in-ride` → render the Finish Ride bar + in-ride timer; re-draw pickup pin.
- If a journey is very old (e.g. `waitStart` > 24h ago), still resume but the "Welcome
  back" card offers **Resume** / **Discard** so a forgotten journey is easy to clear.

## Components / responsibilities

- **`journeyStore`** — read/write/clear localStorage; single source of truth for state + timestamps.
- **`journeyUI`** — render/tear down the docked bars, status chip + live timer, and the
  dialogs (choose-action, ride-details sheet, what's-next, welcome-back). Pure DOM +
  the app's existing CSS tokens (new rules added to `style.css`).
- **`journeyFlow`** — the transitions (start/giveUp/gotRide/finish/nextRide/end) wiring
  store + UI + geolocation + submission together.
- **map.js hooks** — long-press and bubble-tap open choose-action; expose `map`,
  `locationMarker`, `setupLocationSelection`, `findNearbySpotMarker`.

## Error handling & edge cases

- **GPS denied** at start or finish → manual pin (existing selection UI). Never a dead end.
- **Reload** mid-flow → resume from last persisted state; timers recompute from timestamps.
- **Logged out** at Start Hitching → login redirect + resume via `pendingStart`.
- **Submit failure** (network / Nostr) → state retained, retry, or hand off to full form.
- **Clock**: all durations derive from stored epoch-ms diffs, so they are reload-safe.
- **Only one active journey** at a time; entry points are disabled/hidden while `waiting`
  or `in-ride` (long-press/bubble-tap during a journey does nothing or re-shows the bar).

## Testing

No JS/browser test harness exists (Python/pytest only) and the flow is geolocation +
touch driven, so verification is **manual via the cloudflared tunnel on mobile**, walking
each transition, plus reload-resume and GPS-denied paths. If any server endpoint is added
or changed, cover it with a pytest in `tests/`. (Reuse of the existing `/ride` submission
means no new endpoint is expected.)

## Open implementation details (resolve in planning)

- Exact submission mechanism at Finish Ride: `fetch` POST to the existing ride endpoint
  and stay on the map (preferred, smooth), vs. hand-off to `/ride` with auto-submit.
  Preference: `fetch` + on-map success, with full-form hand-off as the failure fallback.
- Precise DOM/CSS placement of the docked bar relative to the locate + zoom controls.
