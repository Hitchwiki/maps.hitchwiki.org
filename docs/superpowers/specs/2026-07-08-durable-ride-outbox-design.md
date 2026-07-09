# Durable Ride Outbox — Design

**Date:** 2026-07-08
**Status:** Approved, ready for implementation
**Branch:** `feature/in-ride-hitching-tracker`
**Related:** [2026-07-02-in-ride-hitching-tracker-design.md](2026-07-02-in-ride-hitching-tracker-design.md)

## Problem

Hitchhikers finish rides in places with poor or no connectivity (you just got
dropped off on a remote roadside). Today, when the `POST /ride` submission fails
(offline / relay down / server error), the in-ride journey stays stuck in the
`in-ride` state, an error is shown, and the user must manually re-tap Finish.
If they close the app, tap End, or clear state, the ride log is lost.

The ride data at Finish time already lives in `localStorage` (the `journeyStore`),
so nothing is *technically* lost yet — but there is no automatic retry, the
journey is stuck in limbo, and the log is fragile. "Give Up" is worse: it
redirects to the server-rendered `/ride` form, which will not even load offline.

## Goal

Never lose a ride log because connectivity was unavailable. When a submission
can't go through, save it durably, tell the user it's safe, complete the
journey, and upload it automatically when connectivity returns.

## Decisions (from brainstorming)

1. **Failure UX:** Save & notify, then auto-retry. The user is told the ride is
   saved and will upload later; the journey completes normally.
2. **Scope:** Cover the in-ride **Finish** submission and **Give Up**. (Past-ride
   logging and edits keep today's behavior for now.)
3. **Retry engine:** Flush while the app is open — on enqueue, on page load, on
   the `online` event, and on a light interval. No service worker (Background
   Sync API is unsupported on iOS Safari, a large share of users).
4. **Pending UI:** A small tappable chip that opens a detail sheet listing
   pending/failed rides with **Retry now** and **Discard** (for failed items).
5. **Also:** During `in-ride`, a long-press on the map drops a destination pin
   and finishes the ride at that spot (a gesture alternative to Finish → GPS).

## Architecture

### 1. Enqueue before the network, not after

The one structural change: Finish / Give Up **write the submission to a durable
outbox first** (so it is safe the instant the user acts), *then* attempt upload.
The journey completes immediately regardless of network state.

```
Old:  Finish → POST → maybe fail → stuck in-ride
New:  Finish → enqueue(outbox) → journey proceeds → flushOutbox() (now + later)
```

### 2. The outbox — `inride.outbox` in localStorage

A JSON array of pending submissions, stored alongside the existing
`inride.journey`. Each item:

```js
{
  id:        "<uuid>",          // client-generated; becomes the Nostr d_tag
  kind:      "finish" | "giveup",
  body:      { …form fields… }, // exactly what POST /ride expects (URLSearchParams-ready)
  createdAt: <epoch ms>,
  attempts:  <int>,
  lastError: "<string|null>",
  status:    "pending" | "failed"  // "failed" = permanent (validation) — no auto-retry
}
```

Store module mirrors `journeyStore`: `get()`, `set(list)`, `add(item)`,
`remove(id)`, `update(id, patch)`. Corruption-safe reads (try/catch → []).

### 3. Idempotency — client-pinned `d_tag`

Each outbox item carries a client-generated `id` (uuid). It is submitted as the
Nostr `d_tag`. Because ride events are **kind 36820 (parameterized replaceable)**,
any retry with the same `d_tag` *replaces* the event on the relay instead of
duplicating it. So a lost-response-after-success can never create a double ride.

Backend changes:
- `HitchhikingDataStandardToNostrPoster.post(record, tags=None, d_tag=None)` —
  when `d_tag` is provided (and `tags is None`, i.e. a new ride), use
  `f"{record.source}-{d_tag}"` instead of generating a fresh uuid. Source stays
  server-authoritative; the client supplies only the uuid.
- `POST /ride` new-ride branch reads optional `client_d_tag` from the form and
  passes it to `poster.post(..., d_tag=client_d_tag)`.
- The relay publish is wrapped so a relay/connection failure returns JSON
  `{ok: false, error, transient: true}` with HTTP **503**, letting the client
  classify it as transient. (Today such failures escape the `except` clause and
  surface as a bare 500; the client already treats 5xx/unparseable as transient,
  so this is a robustness improvement, not a correctness prerequisite.)

### 4. Flush engine — `flushOutbox()`

Walks `status === "pending"` items and POSTs each to `/ride` with the
`X-Requested-With: inride` header and `client_d_tag = item.id`. Classifies:

- **Success** (`res.ok === true`) → `outbox.remove(id)`.
- **Permanent** (HTTP 400 with `{ok:false}` and not `transient`) → validation
  error; `update(id, {status:"failed", lastError})`. No further auto-retry;
  surfaced in the pending sheet for manual Retry / Discard.
- **Transient** (network throw, HTTP 5xx, 503, or unparseable body) → keep as
  pending; `update(id, {attempts: attempts+1, lastError})`; try again later.

Concurrency guard: a module-level `flushing` flag prevents overlapping flushes
(the interval + `online` event + enqueue can all fire close together).

Triggers (all while the app is open):
- Immediately after `enqueue`.
- On page load, in the existing init-on-load path (next to journey resume).
- On the `window` `online` event.
- On a `setInterval` (~30 s) that runs only while the outbox has pending items
  (started when items are added, cleared when it drains, to avoid a idle timer).

### 5. Capture flows

**Finish** (`journeyFlow.finish` / `completeFinish` / long-press):
Build the same body as today (`submitRide`'s URLSearchParams), assign
`id = uuid()`, `enqueue({kind:"finish", body, id})`, then `journeyFlow.whatsNext()`.
The actual upload is `flushOutbox()`, not an inline POST. If offline at enqueue
time, show the one-time toast "Saved — will upload when you're back online."

**Give Up** (`journeyFlow.giveUp`): replace the `/ride` redirect with a slim
inline sheet (a trimmed "How was the spot?" — **rating required + optional
comment**, no vehicle/signal chips since no ride happened). On save: build a
body with `pickup`, `wait` (pause-aware), `rate`, `comment` (no destination →
backend stores NaN), `enqueue({kind:"giveup", body, id})`, clear the journey,
flush. Submission requirements are satisfied: `POST /ride` needs only a valid
`rate` and valid `pickup` coords; destination/wait/comment/signal are optional.

**Long-press to finish** (new): `inrideOnEntryGesture` currently returns early
and ignores gestures while a journey is active. Change: if the journey is
`in-ride`, route the gesture to `journeyUI.manualPin` seeded at the pressed
latlng → Confirm runs the Finish capture (enqueue) at that point; Cancel returns
to in-ride. Waiting/paused states keep ignoring gestures (one journey at a time).

### 6. Pending UI

- **Chip:** a small fixed pill (e.g. bottom-left, clear of the dock/chip stack)
  reading `⟳ N to upload`, shown whenever the outbox is non-empty. Turns red /
  shows a warning glyph if any item is `status:"failed"`. Rendered/refreshed by
  the outbox store on every mutation and by the flush engine.
- **Detail sheet** (on chip tap): reuses the scrim + bottom-card pattern. Lists
  each item — kind, age, attempts, and error for failed ones — with:
  - **Retry now** (per item or all) → resets `failed` items to `pending` and
    calls `flushOutbox()`.
  - **Discard** (failed items only) → `outbox.remove(id)` after a confirm.
  Pending (not-failed) items show a spinner/"waiting for connection" and are not
  individually discardable (they'll upload on their own).

## Components / boundaries

- `outboxStore` (localStorage CRUD; no UI, no network) — testable in isolation.
- `flushOutbox()` (network + classification; depends on `outboxStore` + fetch).
- `outboxUI` (chip + detail sheet; depends on `outboxStore`, triggers flush).
- Capture changes live in existing `journeyFlow.finish` / `.giveUp` and
  `inrideOnEntryGesture`.
- Backend: `poster.post` d_tag param + `/ride` `client_d_tag` + relay 503 wrap.

## Error handling summary

| Result                                  | Classification | Action                          |
|-----------------------------------------|----------------|---------------------------------|
| `{ok:true}` (200)                       | success        | remove from outbox              |
| `{ok:false}` 400, no `transient`        | permanent      | mark `failed`, surface for retry|
| 503 / 5xx / network throw / unparseable | transient      | keep pending, retry later       |

Client-side validation before enqueue (rating present, pickup present) keeps
permanent failures rare; the `failed` state is a safety net, not the norm.

## Testing

- **Backend (pytest):** `poster.post(..., d_tag=X)` produces an event whose `d`
  tag is `f"{source}-X"`; `POST /ride` with `client_d_tag` round-trips it and
  is idempotent (two posts with same `client_d_tag` → same `d`). Relay failure
  path returns JSON 503 with `transient:true`.
- **Frontend (manual, tunnel + device):** offline Finish → toast + chip + journey
  completes; regain connectivity → chip drains, ride appears. Give Up offline →
  inline sheet → chip; uploads on reconnect. Long-press in-ride → pin → Confirm →
  enqueued. Kill a submission with bad data (forced) → `failed` item in sheet →
  Retry / Discard work. Duplicate check: reconnect after a submission that
  actually succeeded server-side → no second ride (same d_tag replaces).

## Out of scope (YAGNI)

- Service worker / Background Sync (retry after full app close).
- Queuing past-ride logging and ride edits.
- Cross-device outbox sync (outbox is per-device localStorage).
- Co-hitchhiker handling in queued submissions (not part of Finish/Give Up).
