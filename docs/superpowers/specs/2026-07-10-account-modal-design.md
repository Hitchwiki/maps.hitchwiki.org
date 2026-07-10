# Account modal (login + profile without leaving the map) — Design

**Date:** 2026-07-10
**Issue:** #106
**Branch:** `feature/account-modal` (from `main`)

## Problem

The account button is a plain link — `<a href="/me">` (`hitch/templates/map.html:533`). Tapping it unloads the map: an in-progress in-ride journey loses its dock and open sheets, test mode exits, the viewport / open spot pane / planned route are discarded, and returning re-downloads `spots.json` (4.2 MB) and `rides_index.json` (26.5 MB).

## Goal

The avatar opens a **modal**; the map page never unloads. The modal serves both auth states.

**Logged in:** username, insight summary, the 10 most recent rides (expandable), and a link out to the full web profile.
**Logged out:** a short pitch plus "Log in with Hitchwiki".

Out of scope (stays on the web profile): editing, trips, follow/unfollow, notifications, achievement ladders.

## The login constraint

Login is Hitchwiki OAuth2, not a local password form. `oauth.login_oauth` (`hitch/blueprints/oauth.py:47`) redirects to `hitchwiki.org/rest.php/oauth2/authorize`; the callback hard-redirects to `/me`, or `/edit-user` for a first-time user. There is no `next`/return-to. **A modal cannot host the credential form.**

### Popup + postMessage

```
avatar tap → modal (logged out)
    [ Log in with Hitchwiki ]
          ↓ window.open("/login/oauth?popup=1")
    popup: hitchwiki.org/authorize
          ↓ callback (?code=) on OUR origin
    popup renders a tiny page that postMessages the opener, then closes
    modal re-renders logged-in; map never unloaded
```

- `/login/oauth?popup=1` sets `session["oauth_popup"] = True` alongside the existing `oauth_state`. The flag rides the session across the Hitchwiki round trip, so the callback knows the flow began in a popup — the redirect back from Hitchwiki carries only `code` and `state`, nothing of ours.
- The callback, when `oauth_popup` is set, pops the flag and renders `oauth_popup_done.html` instead of redirecting. That page calls `window.opener.postMessage({type:"hitchwiki-auth", ok:true, needsProfile:<bool>}, <our origin>)` and `window.close()`.
- **Security:** the popup page is served from our own origin, so it targets `window.location.origin` explicitly (never `"*"`). The opener validates `event.origin === window.location.origin` **and** `event.source === popupHandle` before trusting the message. The existing CSRF-ish `state` check in `_handle_callback` is untouched and still guards the OAuth exchange itself.
- **Popup blocked** (common on mobile Safari): `window.open` returns `null` (or throws). Fall back to a full-page `location.href = "/login/oauth"` — today's behavior. Ride state already survives in `localStorage`; the viewport is in the URL.
- **First-time users** currently land on `/edit-user`. In the popup flow the callback still creates + logs in the user, but reports `needsProfile: true`; the modal then renders a "Finish setting up your profile" link rather than silently swallowing the step.

## Data

Everything is already computed server-side. No new aggregation.

| Field | Source |
|---|---|
| `total_rides`, `total_distance_km`, `total_waiting_time_min` | precomputed columns on the `user` row (`hitch/models.py:43-45`), written by `show.py` |
| distinct partner count | `_distinct_partner_count(username)` (`user.py:228`) |
| recent rides | `_get_rides_for_user(user)` (`user.py:554`), newest first |

### `GET /me.json`

New route on `user_bp`, modelled on the existing `/user` JSON endpoint (`user.py:64`).

- **Anonymous → `200 {"logged_in": false}`.** Never a 302 to `/login`; the modal needs to render its logged-out state from this response.
- **Logged in → `200`:**

```json
{
  "logged_in": true,
  "username": "kim",
  "needs_profile": false,
  "profile_url": "/me",
  "insights": {"rides": 42, "distance_km": 5312.4, "waiting_min": 980, "partners": 7},
  "rides": [{"d_tag": "...", "created": "2026-07-01T12:00:00", "rating": 4,
             "comment": "…", "type": "own",
             "pickup_lat": 1.0, "pickup_lon": 2.0,
             "destination_lat": 3.0, "destination_lon": 4.0}],
  "rides_total": 42
}
```

- `rides` is capped at **50** (`RIDES_IN_MODAL_CAP`). The modal shows 10 and expands to reveal the rest client-side — no pagination for the MVP. `rides_total` is the untruncated count so the UI can say "showing 50 of 231" and point at the full profile.
- Ride entries are `_extract_ride_info` output minus `submission_sort_key` (an internal sort artifact).

**Caching.** This response is per-user. PR #105 made `/static/*` and `dist/*` publicly cacheable, but that hook is keyed on the `static` / `catch_all` endpoints, so a route endpoint like this is untouched and keeps `Vary: Cookie`. That is a fact to *pin down*, not assume: the route sets `Cache-Control: private, no-store` explicitly, and a test asserts it is never `public`. A shared cache serving one user's profile to another is the exact failure mode #105 already had to fix once.

## UI

New `hitch/static/account.js` (browser + CommonJS dual export, like `ride_submit.js`, so the pure parts are node-testable).

- The avatar stays an `<a href="/me">` so it works without JS and for middle-click / "open in new tab". A click handler calls `preventDefault()` and opens the modal instead.
- The modal reuses the in-ride sheet look (scrim + sheet, `disableClickPropagation` so taps never reach Leaflet). It does **not** reuse `journeyUI._openDialog` — that single-flight guard tears down a parent sheet when a second one opens (this bit us in #102). The account modal is a peer, with its own scrim and its own escape/scrim-dismiss.
- Rendering is data-driven off `/me.json`, fetched on open (not at page load — most visits never open it).
- Logged-out body: one sentence on what an account buys, then the login button.

## Testing

- **pytest:** `/me.json` anonymous → `{"logged_in": false}`, 200, not `public`; logged in → the full payload, ride cap honoured, `rides_total` reflects the untruncated count; `Cache-Control` is `private, no-store` and `Vary` does not advertise the response as publicly cacheable.
- **pytest:** `/login/oauth?popup=1` sets the session flag; the callback with the flag renders the postMessage page (not a 302) and clears the flag; without the flag it still 302s to `/me` (no regression to the normal flow).
- **node:** pure render helpers in `account.js` (e.g. the insight-summary formatter and the "showing N of M" logic).
- Manual: popup-blocked fallback on mobile Safari; an in-ride journey and test mode both survive opening/closing the modal.

## Rollout

Additive. The existing `/me`, `/account/<username>`, and `/insights/<username>` pages are unchanged and remain the link target. Reverting is removing the click handler.
