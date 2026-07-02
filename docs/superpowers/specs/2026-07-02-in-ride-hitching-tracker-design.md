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
blocks: the current-location marker, the location-selection/add-spot flow (for "Log a past
ride" and manual-pin fallbacks), and the existing ride submission backend.

**New module:** `hitch/static/inride.js`, loaded after `map.js` in `map.html`. It owns
the journey state, the persistent docked UI, the dialogs, and submission. It calls a
small number of functions/objects exposed by `map.js` (the `map` instance, the location
marker, `setupLocationSelection`, `findNearbySpotMarker`). Rationale: `map.js` is already
~3000 lines; a focused module keeps this feature readable and independently testable.

*Alternatives considered:* (a) put everything in `map.js` — rejected, file is already
large; (b) a server-tracked journey (DB row per journey) — rejected as over-engineered:
the journey is inherently a single-device, single-user, transient thing, and only the
**final** ride needs to be published.

## Geolocation (GPS) usage — discrete only

There is **no continuous or background location tracking**. GPS is read as a
one-shot fix at exactly two points in the flow, plus the pre-existing manual button:

1. **Start Hitching → pickup** — a single fix to set the pickup coords (skipped if we
   already have a fresh fix from the bubble, or if the journey was started from a
   long-pressed location). On denial → manual pin.
2. **Finish Ride → destination** — a single fix to set the destination. On denial →
   manual pin.

**Retry on failure.** A "fix" here means up to **3 attempts**: if `getCurrentPosition`
times out or returns a position error (but *not* a permission denial — that is terminal
and goes straight to the manual-pin fallback), retry, up to three tries total, before
reporting failure. Only after the third failed attempt do we surface the error / offer the
manual pin. This applies to the two data-capturing fixes above and to the manual locate
button. Each attempt uses a bounded timeout so three tries stay responsive.

**The locate/GPS button stays an independent "show my location" control in every state
(idle, waiting, in-ride).** Tapping it pans the map and drops/updates the location bubble
as it does today — it **never** captures pickup or destination, and **never** advances or
interrupts the journey. The two data-capturing fixes above are triggered internally by
the Start Hitching / Finish Ride buttons, not by the locate button.

Because entry points are disabled during an active journey (see below), tapping the
location **bubble** while `waiting`/`in-ride` does nothing (it does not re-open the
choose-action dialog) — so a mid-ride "where am I?" tap on the GPS button is always safe.

**The locate control is present on the persistent map states** — before initiating a ride
(`idle`), and while `waiting`, `paused`, or `in-ride` — so the user can re-center or refresh
their fix throughout a journey. It is **not** shown on the transient dialog/sheet views
(choose-action, soft-login, ride-details sheet, what's-next, set-waiting-spot, resume);
those are brief and dismiss back to a state where it is present again. On `idle` the
controls are unchanged (the existing separate mode switcher + locate button). During a
journey they are combined into the cover-flow stack below.

### Map controls during a journey — cover-flow stack

Today the bottom-right stacks the map-mode switcher (Spots / Heatmap / Countries) above the
locate button and the zoom control. During a journey the docked bar + status chip occupy
the bottom, so to keep the map controls reachable **and** give access to the heatmap /
country map variants mid-journey **without crowding**, the locate button and the three
map-variant buttons are combined into a single **cover-flow stack** (one control slot),
using the existing plain white control buttons as the "covers":

- **Collapsed:** a single button — the most-recently-used of {Locate, Spots, Heatmap,
  Countries} — with a small offset card + layers badge hinting a flip-stack behind it.
  Defaults to **Locate** (`fa-location-crosshairs`) when a journey begins.
- **Tap** the collapsed button → the four buttons flip into a horizontal **3-D cover-flow**:
  the centre button is face-on (**= the current selection**), neighbours tilted back; paging
  dots show position. Buttons are Locate, Spots (`fa-location-dot`), Heatmap (`fa-fire`),
  Countries (`fa-earth-europe`). **No text labels** — the icon + the live map preview behind
  carry the meaning.
- **Swipe** left/right to bring another button to centre; **tapping** a button (or the
  centre) applies it — it slides to centre, its action runs (locate, or switch map mode),
  and the flow **collapses** onto it. Tapping outside collapses with no change.
- The collapsed stack **and** the expanded cover-flow are positioned **above** the zoom
  control (which itself is pushed up to clear the docked bar + status chip), so **nothing
  ever covers the zoom control** or the docked buttons.

Selecting Heatmap/Countries only swaps the map layer; it never affects journey state,
timers, pins, or the docked buttons. Locate behaves exactly as today (independent "show my
location"). This reuses the existing `setMapMode` / `toggleHeatmap` and locate logic — only
the presentation (collapse into one cover-flow) is new, and only while a journey is active.

## State machine

```
                 ┌──────────────── "Log a past ride" (existing add-spot flow) ───┐
                 │                                                                 │
  idle ──long-press / bubble-tap──▶ choose-action ──Start Hitching──▶ waiting     │
                 │                                  (anon → login prompt) │        │
                 └──tap outside: cancel──────────────────────────────────┘        │
                                                                                   ▼
   waiting  ⇄ Pause / Resume ⇄  paused        (wait timer only counts active segments)
   waiting ──Give Up──▶ Add-Spot ride form (prefilled wait + comment) ──save──▶ idle
   waiting ──Got a Ride!──▶ ride-details sheet ──save──▶ in-ride
   in-ride ──Finish Ride──▶ capture destination (auto-GPS / manual) ──submit──▶ whats-next
   whats-next ──Next Ride──▶ set-waiting-spot ──▶ waiting   (new leg, fresh timers)
   whats-next ──End Hitch──▶ idle
```

Persisted states: `idle` (nothing stored), `waiting`, `paused`, `in-ride`.
`choose-action`, `whats-next`, `set-waiting-spot`, and the details sheet are transient
dialogs (not persisted; if the app closes while one is open, we resume the last persisted
state — `waiting`, `paused`, or `in-ride`). Pause applies to **every** waiting phase — the
initial wait and each post-drop-off leg (they are all the `waiting` state).

## Entry points → choose-action dialog

Two ways to open the **choose-action** dialog at a location:

1. **Long-press** a map location (currently goes straight to add-spot). This now opens
   the choose-action dialog first.
2. **Tap the current-location bubble** (`locationMarker`). Requires the user to have
   tapped the GPS button first (that is what creates the bubble). The bubble becomes
   interactive and opens the dialog at its position.

**Dialog (Variant A — stacked, dark scrim):**
- Title: "This spot"
- Body: "Track a ride from here now — or log a ride you already got."
- **Start Hitching** — green primary (`--green #1a9850`); live tracking.
- **Log a past ride** — secondary ghost/blue-outline (clock-rotate-left icon). This is the
  existing add-spot flow, **renamed** so it clearly reads as retrospective — users
  accustomed to "Add Spot" as the way to *start* shouldn't confuse it with live tracking.
- Tap anywhere outside the card (on the scrim) cancels and returns to `idle`.

"Log a past ride" preserves the current add-spot behavior exactly
(`setupLocationSelection('select-pickup', … isNewSpot)` with its snap-to-nearby-spot and
confirm card); only the label/framing changes.

## Accounts — soft login prompt

No hard gate. **Logged-in** users go straight from Start Hitching to `waiting`.

If the user is **anonymous**, Start Hitching first shows a small prompt (title:
"Track your rides?"):
- **Log in** — stash the intended pickup in `localStorage` (`inride.pendingStart`),
  navigate to `/login?next=/`. On return logged-in, resume **straight to `waiting`** at
  the stashed location and clear `pendingStart`. If they return still anonymous
  (abandoned login), discard `pendingStart` and do nothing.
- **Continue anonymously** — proceed to `waiting` immediately; the final ride submits
  anonymously (as today's anonymous spot-add).
- Tapping outside cancels back to `idle`.

The final ride submits through the existing path, which already supports anonymous
submission. Logged-in users' rides are attributed/owned exactly as today. "Log a past ride"
is unaffected (anonymous as today). Client-side, `inride.js` reads the `is_logged_in` flag
that `map.html` already renders into the page to decide whether to show the prompt.

## Waiting state

- Pickup coordinates = the chosen location. For "Start Hitching", if we have a fresh GPS
  fix (bubble tap) we use it; otherwise we prompt GPS permission, and on denial the user
  drops the pin manually (reusing the location-selection pin UI). The waiting pin is
  **draggable** so the user can nudge it to the exact spot at any time.
- **Active-wait accumulator (pause-aware).** Wait time is measured as the sum of *active*
  segments, not raw wall-clock. Two fields track it:
  - `waitAccumMs` — active ms banked from completed segments (starts at 0).
  - `waitSegmentStartMs` — start of the currently-running segment (`null` while paused).

  Current wait = `waitAccumMs + (waitSegmentStartMs ? now − waitSegmentStartMs : 0)`.
  When `waiting` begins, `waitSegmentStartMs = now`. This is reload-safe and pause-safe.
- **Persistent docked bar** (`position:fixed`, above zoom controls), restored on reload:
  - **Give Up** — big red (`--red #d73027`)
  - **Got a Ride!** — big green (`--green`)
  - **Pause** — compact tertiary control (icon + "Pause"), e.g. on the status-chip row so
    the two big primary buttons stay uncrowded.
- **Status chip** above the bar shows a live `Waiting · HH:MM:SS` timer (ticks each
  second; the authoritative value is always the accumulator above, so reloads and pauses
  are exact).

### Pause / Resume

Tapping **Pause** (from any waiting phase — initial or post-drop-off) enters the persisted
`paused` state: bank the running segment (`waitAccumMs += now − waitSegmentStartMs`), set
`waitSegmentStartMs = null`, and freeze the timer.

Paused UI **mirrors the waiting bar**: the docked bar keeps **Give Up** (red) + **Got a
Ride!** (green), but **Got a Ride! is greyed-out/disabled** until the user resumes (you
can't board while paused). The **Resume** control lives in the **status chip**, in the same
spot the Pause pill occupied — the chip reads `Paused · waited MM:SS  ▶ Resume`. Tapping
Resume sets `waitSegmentStartMs = now`, re-enables Got a Ride!, and returns to `waiting`.
Give Up stays active throughout. Pausing keeps a meal break or an overnight stop out of the
recorded wait time.

### Give Up

Opens the **existing Add-Spot → ride form** flow, pre-filled with:
- `wait` = `round(currentWaitMs / 60000)` minutes (the pause-aware accumulator — excludes
  paused time)
- an empty comment field for the user to fill
- pickup = the waiting location

Rating stays **required** (unchanged form rule — the user rates the spot). On save, the
form submits through the normal path; the journey state is cleared to `idle`.

Mechanism: reuse the existing `sessionStorage.rideFormData` prefill that
`selectLocation()` already uses, then navigate to `/ride`.

## Got a Ride! → ride-details sheet

Tapping "Got a Ride!" records `t_gotRide` (= departure time, and the end of waiting) and
opens a **slim bottom sheet** (not the full form), titled **"How was the spot?"**:
- Star **rating** (required)
- **Vehicle kind** chips (Car/Truck/Van/…), default Car
- **Signal** chips (Thumb/Sign/Asking)
- **Comment** (optional)
- **"Ride On!"** primary button → transitions to `in-ride`
- **"＋ Add driver / vehicle details"** link → opens the full ride form for power users
  (their in-sheet selections carried over via the existing sessionStorage prefill).

The captured details + `t_gotRide` + pickup + final wait duration (the frozen accumulator)
are stored in the `in-ride` localStorage record; **submission is deferred** to Finish Ride
(when the destination is known).

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
- **Next Ride** — green: start a new leg. The just-submitted ride keeps its **actual
  drop-off** as its destination; the new leg's **waiting location is set separately** (see
  below) because hitchhikers are often dropped at one spot and walk to a nearby, better
  one. → `set-waiting-spot`.
- **End Hitch** — grey: clear journey state → `idle`.

### set-waiting-spot (new leg)

A lightweight confirm step (reusing the location-selection pin UI), **defaulting the pin
to the drop-off** so the common "wait where I was dropped" case is a single tap:
- A draggable pin pre-placed at the drop-off, plus a **"Use my location"** (GPS) button
  and free tap/drag to move it — for when the good spot is a short walk away.
- **Confirm** → resets the wait accumulator (`waitAccumMs = 0`, `waitSegmentStartMs = now`),
  sets pickup to the confirmed location, increments `legIndex`, and enters `waiting`.

This keeps each leg's pickup and the previous leg's drop-off independent and accurate,
while staying one-tap in the usual case.

## Data mapping (zero-typing capture)

Reusing the existing ride/Nostr shape (`stops[0]` = pickup, `stops[-1]` = destination):

| Ride field | Source |
|---|---|
| pickup lat/lon (`stops[0].location`) | journey start location |
| `waiting_duration` (`PT<n>M`) | pause-aware active-wait accumulator at Got-a-Ride, rounded to minutes (excludes paused time) |
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
  "state": "waiting | paused | in-ride",
  "pickup": { "lat": 48.20, "lon": 16.37 },
  "waitAccumMs": 0,               // active wait banked from completed segments
  "waitSegmentStartMs": 1751459200000,  // current segment start; null while paused
  "gotRideMs": null,              // set at Got-a-Ride (departure time)
  "finalWaitMs": null,            // frozen active-wait accumulator at Got-a-Ride
  "details": null,                // rating/vehicle/signal/comment once Got-a-Ride is saved
  "legIndex": 0                   // increments on Next Ride (informational)
}
```
Key `inride.pendingStart`: `{ "lat": …, "lon": … }` — set only when an anonymous user
picks "Log in" from the soft prompt, so the intended start survives the login redirect;
cleared on return.

Written on every transition; read once on page load to rehydrate the docked UI + timer.

## Resume on load

On map init, `inride.js` reads `inride.journey`:
- `waiting` → render the Give Up / Got a Ride bar + running waiting timer; re-draw pickup pin.
- `paused` → render the waiting bar (Give Up + greyed-out Got a Ride!) + frozen
  `Paused · waited … ▶ Resume` chip; re-draw pickup pin.
- `in-ride` → render the Finish Ride bar + in-ride timer; re-draw pickup pin.
- If a journey is very old (e.g. current segment started > 24h ago), still resume but the
  "Welcome back" card offers **Resume** / **Discard** so a forgotten journey is easy to clear.

## Components / responsibilities

- **`journeyStore`** — read/write/clear localStorage; single source of truth for state + timestamps.
- **`journeyUI`** — render/tear down the docked bars (waiting / paused / in-ride), status
  chip + live timer, the cover-flow map-control stack (locate + Spots/Heatmap/Countries),
  and the dialogs (choose-action, soft-login, ride-details sheet, what's-next,
  set-waiting-spot, welcome-back). Pure DOM + the app's existing CSS tokens (new rules added
  to `style.css`); the stack members reuse the existing `setMapMode` / `toggleHeatmap` /
  locate logic.
- **`journeyFlow`** — the transitions (start / pause / resume / giveUp / gotRide / finish /
  nextRide / setWaitingSpot / end) wiring store + UI + geolocation + submission together.
- **map.js hooks** — long-press and bubble-tap open choose-action; expose `map`,
  `locationMarker`, `setupLocationSelection`, `findNearbySpotMarker`.

## Error handling & edge cases

- **GPS denied** at start or finish → manual pin (existing selection UI). Never a dead end.
- **GPS fix fails** (timeout / position-unavailable) → retry up to 3 attempts before
  reporting failure and offering the manual pin. Permission denial skips retries (terminal).
- **Locate control** → shown before initiating a ride (`idle`) and while `waiting` /
  `paused` / `in-ride`; not on the transient dialog/sheet views. Independent "show my
  location", never feeds the flow. During a journey it and the map-variant switcher become
  one cover-flow stack (tap-to-open, swipe/tap a cover to select, collapses onto the
  selection), positioned above the zoom control so nothing overlaps.
- **Reload** mid-flow → resume from last persisted state; timers recompute from timestamps.
- **Anonymous** at Start Hitching → soft prompt (Log in / Continue anonymously); never blocks.
- **Submit failure** (network / Nostr) → state retained, retry, or hand off to full form.
- **Clock**: all durations derive from stored epoch-ms diffs (accumulator for wait), so
  they are reload-safe and pause-safe.
- **Pause**: available in every waiting phase (initial and each post-drop-off leg); paused
  time is excluded from `waiting_duration`. Resume-on-load restores the paused UI frozen.
- **Drop-off ≠ next waiting spot**: Next Ride keeps the finished ride's real drop-off and
  lets the new leg's waiting location be set separately (defaulting to the drop-off).
- **Only one active journey** at a time; entry points are disabled/hidden while `waiting`,
  `paused`, or `in-ride` (long-press/bubble-tap during a journey does nothing).

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
