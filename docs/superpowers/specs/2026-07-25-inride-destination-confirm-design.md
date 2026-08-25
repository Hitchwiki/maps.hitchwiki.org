# In-ride Finish: always confirm the drop-off location

**Date:** 2026-07-25
**Status:** Approved, ready for planning

## Problem

Pressing **Finish Ride** never asks where the ride ended. `journeyFlow.finish`
(`hitch/static/inride.js:374`) calls `getFixWithRetry()` with no UI and uses whatever the
GPS returns as `destination_lat/lon`. The manual pin picker only appears when GPS is
*denied or exhausted*, so a phone with location granted goes straight from the details
nudge to the would-ride-again sheet.

Two consequences:

1. **The recorded destination is silently wrong whenever Finish is pressed late.** People
   press Finish once they have settled somewhere — a café, a hostel, home in the evening —
   and the ride is logged as ending there rather than where the driver dropped them.
2. **Mid-sequence it looks like the app skips the drop-off entirely.** The only pin picker
   a multi-leg hitchhiker ever sees is the green "Where are you waiting?" one from
   `setWaitingSpot`, so Finish appears to jump straight to choosing the next waiting spot.

Neither the user nor the data can tell a GPS-at-drop-off from a GPS-three-hours-later.

## Goals

- Every finished ride gets a drop-off location the hitchhiker actually confirmed.
- The confirm happens on **every leg**, including the last one before End Hitch.
- Finish never blocks on a GPS fix, and never becomes a dead end when GPS fails.
- Mid-sequence, confirming the drop-off must not cost a second near-identical map screen.

## Non-goals

- Changing what "destination" means. It stays the drop-off point, not where the driver was
  ultimately headed.
- Touching the `/ride` form's destination picker.
- Backfilling or correcting destinations on rides already submitted.

## Design

### 1. Flow change in `journeyFlow.finish`

```
details nudge  →  ►DROP-OFF CONFIRM (map pin)◄  →  would-ride-again  →  submit
```

The unconditional pin step replaces the silent
`getFixWithRetry().then(askAndSubmit, manualPin)` branch at `inride.js:401`.

`finish()` is the only route into `completeFinish`, and `completeFinish` is the only route
to `whatsNext` → next leg. There is no path that reaches leg N+1 without passing through
Finish, so making the step unconditional here covers every leg and the final one alike —
no per-leg special casing.

Unchanged on purpose:

- **`finishMs` is still stamped at the top of `finish()`** (`:381`), before the picker
  opens. The backend asserts `arrival > departure`; stamping early is what keeps the added
  prompt delay out of the recorded arrival time. Same reason the would-ride-again sheet was
  safe to add.
- **Cancel keeps today's `manualPin` semantics:** stay in the `in-ride` state, clear the
  busy flag, leave Finish tappable. Aborting the picker must never discard the journey.

### 2. One pin picker instead of two

`manualPin` (`:849`) and `setWaitingSpot` (`:1743`) are the same widget with different
titles, marker colours, and — the actual hazard — different output contracts. `manualPin`
yields `{lat, lon}`; `setWaitingSpot` yields a Leaflet `LatLng` with `.lng`. The comment at
`:860` documents a real bug this already caused: a raw `LatLng` reached `buildFinishBody`
and produced `destination_lon: undefined`, which the backend rejected without a clear
error. Adding a third copy of the widget for the drop-off would be the third chance to hit
the same trap.

Both collapse into one function:

```js
journeyUI.pinConfirm({
  title, hint, confirmLabel,
  seed,        // {lat, lon} | null → map centre
  color,       // "orange" (drop-off) | "green" (waiting spot)
  autoLocate,  // request GPS in the background, snap the pin if untouched
  myLocation,  // show the "Use my location" button
  onConfirm,   // ALWAYS receives {lat, lon}
  onCancel,
})
```

- **`onConfirm` always receives `{lat, lon}`.** Leaflet's `.lng` never escapes the picker,
  which retires the contract mismatch for good.
- **Boundary normalisation instead of a cross-file contract change.** `journeyFlow.start`
  and `journeyFlow.nextRide` currently read `latlng.lng` and are also called with genuine
  Leaflet `LatLng`s from outside this module (`map.js:2395`, `inride.js:2265`). Each gets a
  small `toLatLon()` normaliser at its entry accepting either shape, so no call site in
  `map.js` has to change.
- **Behaviour currently present in only one of the two, now in both:** the `_picking` stack
  guard, the `_setPin` long-press reposition hook, the `inr-picking` body class that
  neutralises overlay markers, and the "Use my location" button.

Drop-off uses the orange marker and the title "Where did you get out?"; the waiting-spot
picker keeps its green marker and existing wording.

### 3. GPS: background request, snap only if untouched

The picker opens **immediately**, seeded at the current map centre, and fires
`getFixWithRetry()` in parallel. When a fix lands the pin moves and the map recentres —
but only while a `touched` flag is still false. `touched` is set by the marker's
`dragstart`, by a map click, and by the `_setPin` long-press hook, so a fix arriving 20 s
late can never yank a pin the user has already placed.

"Use my location" renders as a disabled "Locating…" while a fix is in flight and **shares
the in-flight promise** with the background request, so tapping it never starts a second
geolocation call. On failure it surfaces the existing `journeyUI.error()` toast and leaves
the pin where it is — Finish stays completable with a dragged pin, so a denied or broken
GPS is never a dead end.

### 4. "What's next?" splits into three actions

Because the drop-off is now user-confirmed, forcing a second map screen to re-confirm
essentially the same point would be pure friction. `journeyFlow.whatsNext` therefore offers:

```
Ride saved — dropped off here.

  [ Next ride from here ]   → nextRide(dropoff) directly, no second picker
  [ Wait somewhere else ]   → pinConfirm (green) seeded at dropoff, then nextRide
  [ End Hitch           ]   → journeyFlow.end()
```

Cancelling the green picker returns to this dialog, as `setWaitingSpot`'s `onCancel` does
today — otherwise the user would be stranded with no way to reach End Hitch.

The common case (wait where the driver left you) is one tap. Walking to a better on-ramp is
still recordable in one extra tap — dropping that capability would silently degrade spot
data, since the walked-to spot is the one worth logging.

`journeyUI.dialog` already renders an arbitrary `actions` array and `.inr-actions` is
`flex-wrap: wrap`, so three buttons wrap rather than overflow. Labels must stay short
enough to stay readable at 320 px width.

## Error handling

| Case | Behaviour |
| --- | --- |
| GPS denied or times out | Picker already open at map centre; error toast; user drags the pin |
| Picker cancelled | Journey stays `in-ride`, busy cleared, Finish tappable again |
| Fix arrives after the user moved the pin | Ignored (`touched` guard) |
| `window.map` / Leaflet missing | `pinConfirm` clears busy and returns, as `manualPin` does today |
| Offline at Finish | Unchanged — the outbox already queues the body durably |

## Testing

`tests/ride_submit.test.js` already asserts the destination reaches the POST body via
`buildFinishBody`, and must stay green; `tests/test_inride_submit.py` and
`tests/test_inride_outbox.py` cover the submit path and must stay green too.

`pinConfirm` is DOM code, and `CLAUDE.md` forbids installing or running a headless browser
on this prod host, so the rest is code review plus a manual browser pass by the user:

1. Finish with GPS granted → orange picker appears, pin snaps to current location.
2. Drag the pin before the fix lands → pin does **not** jump when the fix arrives.
3. Cancel the picker → journey still in-ride, Finish works on a second press.
4. Deny GPS → picker still opens, error toast, dragged pin confirms fine.
5. Mid-sequence: Finish → "Next ride from here" → waiting dock, no second picker.
6. Mid-sequence: Finish → "Wait somewhere else" → green picker seeded at the drop-off.
7. Last leg: Finish → drop-off confirm → End Hitch.
8. Verify the submitted ride has two stops with the confirmed destination.

## Files touched

- `hitch/static/inride.js` — `pinConfirm`, `journeyFlow.finish`, `whatsNext`, `toLatLon`
  normalisers on `start` / `nextRide`. `manualPin` and `setWaitingSpot` are **deleted**, not
  wrapped — between them they have three call sites (`:405`, `:434`, `:1860`), all of which
  move to `pinConfirm` directly.
- `hitch/static/style.css` — only if the three-action dialog needs layout adjustment.
