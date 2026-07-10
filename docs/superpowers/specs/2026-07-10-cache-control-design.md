# Cache-Control for static assets and generated data — Design

**Date:** 2026-07-10
**Branch:** `feature/cache-control` (from `main` @ `5e8caf8`)
**Status:** Approved, ready for implementation plan

## Problem

Every file the app serves comes back with `Cache-Control: no-cache` and
`Vary: Cookie`. Both actively defeat caches that would otherwise work:

- **`no-cache`** forces the browser to revalidate on *every* request. Werkzeug
  emits it because `catch_all` and Flask's static route call
  `send_from_directory` with no `max_age` (and `SEND_FILE_MAX_AGE_DEFAULT` is
  unset). `no-cache` still *stores* the body, but the browser must make a
  conditional round-trip before reusing it — and whenever the file changed, it
  re-downloads the whole thing.
- **`Vary: Cookie`** (injected by the session/login layer) fragments the cache
  per distinct `Cookie` header, so a returning visitor whose session cookie
  changed re-fetches from scratch and no shared/CDN cache can be reused.

Measured impact (live prod headers):

| File | Size | Current headers |
|---|---|---|
| `rides_index.json` | **26.5 MB** | `no-cache`, `Vary: Cookie` |
| `spots.json` | **4.2 MB** | `no-cache`, `Vary: Cookie` |
| `static/map.js` | 141 KB | `no-cache`, `Vary: Cookie` |

`rides_index.json` and `spots.json` regenerate every ~10 min (`show.py` cron),
so a returning visitor frequently pays a full multi-MB re-download. The static
assets already carry a `?v=<mtime>` cache-buster from `asset_url()` (`hitch/__init__.py`),
yet `no-cache` means that cache-busting buys nothing — a stable URL still
re-downloads.

Data is already up to ~40 min stale by design (`fetch_nostr` every 30 min +
`show` every 10 min), so a few extra minutes of client-side staleness costs
nothing perceptible.

## Goals

1. `/static/*` (cache-busted URLs) → long-lived immutable caching.
2. Big `dist/*` generated data → short `max-age` + `stale-while-revalidate`.
3. Stop `Vary: Cookie` from fragmenting these public responses.

Non-goals: changing the service worker (`sw.js` stays network-first), caching
rendered HTML, or caching authenticated / route-driven JSON endpoints.

## Design

### 1. Static assets — `/static/*`

Served by Flask's built-in static route; URLs already include `?v=<mtime>`
(changes on every file edit), so the body at a given URL is immutable.

```
Cache-Control: public, max-age=31536000, immutable
Vary: Accept-Encoding
```

- 1 year + `immutable` — returning visitors never re-request `map.js`,
  `style.css`, or marker images until their URL changes.
- Safe because a content change changes the `?v=` query, which is a new cache
  key. The rendered HTML that references these URLs is **not** long-cached (see
  §3), so new `?v=` links propagate on the next page load.

### 2. Generated data — `dist/*` via `catch_all`

```
Cache-Control: public, max-age=300, stale-while-revalidate=600
Vary: Accept-Encoding
```

- `0–5 min`: served from cache with no network round-trip.
- `5–15 min`: served stale instantly while the browser refreshes in the
  background (`stale-while-revalidate`).
- `>15 min`: normal revalidation — `ETag`/`Last-Modified` are preserved, so an
  unchanged file returns `304 Not Modified` (tiny), and the full body downloads
  only when the file actually changed.
- Worst-case added staleness: ~5 min on top of the existing ~40 min pipeline
  lag — negligible.

Applied **uniformly to all `dist/*` files** for simplicity. Files with a slower
regeneration cadence (`events.json` daily, `country_ratings.json` monthly) just
refresh a little more often than strictly necessary — harmless.

Applied on **both** branches of `catch_all`:
- the precompressed `.gz` sidecar branch (which already sets
  `Vary: Accept-Encoding` and `Content-Encoding: gzip`), and
- the plain `send_from_directory` branch.

`Vary` is set to `Accept-Encoding` (correct — the response genuinely varies by
gzip vs plain), replacing the injected `Vary: Cookie`.

### 3. Deliberately untouched

- **Rendered HTML** (`/`, `/spot/…`, `/copyright`): stays revalidate/`no-cache`
  so a new deploy's `?v=` asset links are picked up immediately. This is the
  invariant that makes §1's immutable caching safe.
- **`sw.js`**: stays `no-cache`. The service worker is the update mechanism and
  must never be long-cached, or clients get stuck on an old worker.
- **Route JSON endpoints** (e.g. `/driver_info_choices.json`): left as-is —
  small, and not part of the `dist/` static-file path.

## Implementation approach

A single `after_request` hook in `register_routes` (or `create_app`), keyed on
`request.path`:

- `request.path.startswith("/static/")` → set the §1 immutable header.
- the `dist/*` responses from `catch_all` → set the §2 SWR header. Identify
  these by the request being handled by `catch_all` (e.g. endpoint name
  `catch_all`) rather than by guessing from the path, so route endpoints and
  HTML are never caught.
- In both cases, replace `Vary: Cookie` with `Vary: Accept-Encoding` and drop
  the `no-cache` that Werkzeug added.

Rationale for `after_request` over per-call `max_age=`: it is one central place,
it can *remove* the `no-cache`/`Vary: Cookie` that other layers inject, and it
keeps `catch_all`'s existing gz logic untouched.

### Risk to verify empirically

`no-cache` + `Vary: Cookie` may be injected during response finalization (the
session/login layer), potentially *after* `after_request` runs. These public
paths never touch the session, so the values should stick — but this must be
**confirmed with live `curl`** against the running server after the change
(assert the final `Cache-Control`/`Vary` on `/static/<asset>` and a `dist/`
file). If a later layer re-adds `Vary: Cookie`, the hook must force-set the
header last (or ensure these responses are session-neutral).

## Testing

- **pytest** (`tests/`): using the Flask test client, request a `/static/`
  asset and a `dist/` file (create a throwaway file under `dist/` in the test
  if none is guaranteed present), and assert:
  - `/static/*` → `Cache-Control` contains `max-age=31536000` and `immutable`;
    `Vary` does not contain `Cookie`.
  - `dist/*` → `Cache-Control` contains `max-age=300` and
    `stale-while-revalidate=600`; `Vary` does not contain `Cookie`.
  - a rendered HTML route (`/copyright`) is **not** long-cached (guards §3).
- **Live curl** verification against `flask run` for the headers above,
  including a gzip request (`--compressed`) to confirm the `.gz` branch keeps
  `Content-Encoding: gzip` + `Vary: Accept-Encoding` alongside the new
  `Cache-Control`.

## Rollout notes

- No data-model or generation changes; headers only. Reversible by removing the
  hook.
- First deploy: clients holding the old `no-cache` copies simply pick up the new
  headers on their next fetch; nothing to invalidate.
