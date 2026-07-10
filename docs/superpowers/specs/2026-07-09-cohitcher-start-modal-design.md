# Co-hitcher start-of-journey modal — design

- **Date:** 2026-07-09
- **Status:** Approved (design); ready for plan
- **Related:** In-ride tracker (`hitch/static/inride.js`), `CoHitchhiker` model, `/ride` route

## Goal

When a hitchhiker starts a journey, give them an immediate, low-friction chance to record
**who else is hitching with them** — surfaced at the natural moment (journey start) rather than
buried in the Finish form. Logged-in users also see confirmation of who they're logging as.

## Flow & entry point

Both "Start Hitching" (long-press choose menu) and "Hitch here" (spot details) funnel through
`journeyFlow.startFromChoose(latlng)`. The modal is inserted there, immediately before the journey
is seeded:

- **Logged in:** show the co-hitcher modal directly. It displays `You're hitching as @<username>`
  plus the co-hitcher entry. "Start hitching" → `journeyFlow.start(latlng, coHitchhikers)`.
- **Not logged in:** the existing "Track your rides?" dialog is unchanged. "Log in" → redirect
  (unchanged, resumes below). **"Continue anonymously"** → the co-hitcher modal (no username line) →
  `journeyFlow.start(latlng, coHitchhikers)`.

Every place that **begins a new journey** must route through the modal, so the modal wraps the
new-journey start (e.g. a `journeyFlow.beginWithCoHitchers(latlng)` helper that shows the modal,
then calls `start`). There are three such sites today, all currently calling `start` directly:
1. `startFromChoose` logged-in branch (inride.js:193).
2. "Continue anonymously" (inride.js:208).
3. **Post-login-redirect resume** (inride.js:1582): after "Log in" → redirect → return, the stashed
   pickup resumes a start. The user is now logged in, so this must show the modal too (username +
   co-hitchers) rather than starting silently.

(Resuming an *existing, already-started* journey on load must NOT re-open the modal — only new starts do.)

Dismissing the modal (scrim tap / ×) aborts the start — no journey begins. There is **no explicit
Skip**: the field is optional, and "Start hitching" begins the journey with zero or more co-hitchers.

## Modal UI

Reuses the established username pattern from the `/ride` form:

- A username input with autocomplete against the existing **`/search_usernames?q=`** endpoint.
- Selected co-hitchers render as removable chips.
- Self-exclusion: a logged-in user cannot add their own username (they are the creator); duplicates
  are de-duped.
- Single primary **"Start hitching"** button. Optional field — the button is always enabled.

Built as an in-app bottom-sheet/modal in `inride.js` (consistent with the other in-ride sheets),
not a page navigation, so the user stays on the map.

## Data model & carry-through

- Co-hitchers live on the **journey object**: `j.coHitchhikers` = array of usernames, set by
  `journeyFlow.start(latlng, coHitchhikers)` and persisted in the localStorage journey, so they
  survive reloads and the soft-login round-trip (resume-on-load restores them with the rest of `j`).
- They are submitted with the ride as the `co_hitchhiker` form field (comma-separated usernames):
  - **Finish:** `buildFinishBody` (`ride_submit.js`) adds `co_hitchhiker: (j.coHitchhikers||[]).join(",")`.
  - **Give Up:** `journeyFlow.giveUp`'s outbox body adds the same field (you waited together, so
    co-hitchers attach to a give-up ride as well).

## Backend

**No new write logic.** `/ride` already processes `co_hitchhiker` (main.py:699): it splits the
comma-separated usernames, writes `CoHitchhiker` rows keyed by the ride's `d_tag` with
`accepted="open"`, and calls `notify_co_hitchhiker_invite`. This block runs before the JSON
response, so in-ride (Finish and Give Up) submissions reach it. Anonymous entries are already
skipped there, and the existing `/accept-co-hitchhiking-ride/<d_tag>` acceptance flow is reused
as-is — an anonymous creator still produces a `d_tag`, so invited users can accept normally.

## Username exposure

`map.html` currently exposes only `window.IS_LOGGED_IN`. Add `window.USERNAME` (from
`current_user`) in the `render_map` template context so the modal can show `@<username>`.

## Edge cases

- Empty co-hitcher list → `co_hitchhiker` omitted/empty → backend writes nothing (unchanged path).
- Reload mid-journey → `j.coHitchhikers` restored from localStorage.
- Soft-login round-trip (anonymous → log in → return) → co-hitchers are entered *after* the login
  choice, so no cross-redirect stashing is needed for them.
- A co-hitcher username that later fails backend validation is handled by the existing `/ride`
  co-hitcher logic (unchanged).

## Testing

- **Frontend:** `journeyFlow.start(latlng, coHitchhikers)` stores `coHitchhikers` on `j`;
  `buildFinishBody` emits `co_hitchhiker` as a CSV; the Give Up outbox body emits `co_hitchhiker`.
- **Backend:** a test that an in-ride `/ride` POST carrying `co_hitchhiker` writes the expected
  `CoHitchhiker` rows (add if not already covered by existing co-hitcher tests).

## Out of scope

- Editing co-hitchers mid-journey or from the in-ride bar (the `/ride` edit flow already covers
  post-hoc editing).
- Any change to the acceptance workflow or notifications.
