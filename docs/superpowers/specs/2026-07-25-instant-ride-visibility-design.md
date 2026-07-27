# Instant ride visibility

**Date:** 2026-07-25
**Status:** Approved design

## Problem

A ride submitted through `/submit` is published to the Nostr relays and nothing else
happens locally. It reaches the local `ride_event` table only when
`fetch_nostr_incremental` runs (up to 5 min later), and reaches the map only when
`show.py` regenerates `dist/` after that (up to 10 min later). So:

- `/ride/<d_tag>` returns **404** for up to ~5 minutes after logging a ride.
- The ride is invisible on the map, and on its `/spot/<spot_id>` page, for up to ~15
  minutes. A ride at a brand-new location has no marker at all in that window.
- The success screen's share card deliberately links to `/spot/<spot_id>` instead of the
  ride, with a comment in `static/share_card.js` explaining that the ride "has no
  permalink yet".
- Editing a ride shows the old text until the next incremental fetch.

The ride's `d` tag is already known before publishing (`build_ride_d_tag`), and
`poster.post()` already returns it — it is simply discarded by the redirect.

## Goals

1. `/ride/<d_tag>` works the instant the submit POST returns.
2. The ride is visible on the map and in the spot pane immediately, **for everyone**, not
   only in the submitting browser.
3. The share card links to the ride's own permalink, and that link previews sensibly.
4. No new heavy work on the request path, and nothing that can drift out of sync with the
   cron pipeline permanently — every shortcut must be superseded by the normal cron data
   rather than competing with it.

## Non-goals

- Running `show.py` (or any part of it) per submission. It reads the whole `ride_event`
  table into pandas; it is a cron job by construction.
- Making the fresh ride participate in derived views: filters, comment search,
  `spots_recent.json`, the routing graph, the heatmap, country stats. Those keep their
  existing cron latency.
- An `og:image` for ride pages (a per-ride map PNG pipeline, mirroring
  `hitch/scripts/route_preview.py`). Explicitly deferred as its own change.
- Fixing the fact that `pynostr` does not verify the relay's OK notice.

## Design

### Part 1 — Write the ride to the local DB at publish time

`HitchhikingDataStandardToNostrPoster.post()` builds, signs and publishes an `Event`, then
returns only the `d` tag. Expose the signed event as well (a second return value, or
`self.last_event`; the existing `d_tag`-returning contract must keep working for the
`publish_ride.py` example module).

In `hitch/blueprints/main.py`, after a successful `post()` on both the new-ride and the
edit branch:

```python
fields = parse_post_to_ride_fields(event.to_dict())
```

`parse_post_to_ride_fields` (`hitch/scripts/nostr_ride_parsing.py`) is the same function
both fetch scripts use, so the row we write has exactly the columns the cron would have
written — no third extraction to keep in sync.

Upsert it on the addressable coordinate `(pubkey, d)`, newest-`created_at`-wins, mirroring
`fetch_nostr_incremental.py`:

- New ride → INSERT.
- Edit → the row already exists under the same `(pubkey, d)`; overwrite every column
  including the primary key `id` (an edit is a new event id under the same coordinate).

Because the event we insert is byte-identical to the one the relay will hand back, the
incremental fetch 5 minutes later sees an equal `created_at` and classifies it
`unchanged`. The shortcut is self-healing: the cron is still the authority, it just has
nothing left to do.

Failures must never lose a published ride: wrap the insert so an exception is logged and
swallowed, then continue to the redirect. The ride is on the relay; the cron will import
it. A local DB hiccup must not turn a successful publish into a 500.

**Consequences, all free once the row exists:**

- `/ride/<d_tag>` renders immediately (it already queries `RideEvent` by `d`).
- The ride shows on the author's profile immediately.
- `_user_owns_ride` / `_user_can_delete_ride` match on content already present, so edit and
  delete work right away instead of after the cron.
- An edit's new text is live at once.

**Known failure mode (documented, not solved):** `pynostr` does not check the relay's OK
notice, so a silently rejected event leaves a local row that no fetch will ever confirm.
The weekly full `fetch_nostr.py` (delete-and-recreate) then drops it. This is strictly
better than today, where such a ride is lost immediately, and it is the same gap
`dist/temporary.json` exists to record. Note it in a comment at the insert site.

### Part 2 — `/pending_rides.json`, served live from the DB

Modelled on the existing `/proposed_spots.json` (`main.py`): served straight from the DB,
not from `dist/`, so it is correct the moment the row is written.

**Cutoff.** `show.py` reads the DB at time T (`pd.read_sql`, line 89) and finishes writing
files minutes later. Using a file mtime as the cutoff would silently skip any ride landing
in that window. So:

- `show.py` captures `snapshot_ts = time.time()` immediately **before** `pd.read_sql`.
- After all files are written (end of the script, after the heatmap block), it writes
  `dist/generated_at.json` = `{"ts": snapshot_ts}`. Writing it last means the file only
  claims a snapshot that is actually on disk.
- The endpoint returns rides with `created_at >= ts`.
- If `generated_at.json` is missing (first deploy, before the next `show.py` run), fall
  back to the mtime of `dist/rides_index.json`. That mtime is *later* than the true
  snapshot, so the fallback under-returns rather than over-returns — it degrades to
  today's behaviour, never to duplicates.

`show.py`'s early exit ("JSON files are up to date") deliberately does **not** refresh
`generated_at.json`. That path is only taken when nothing has been written to the DB since
the last generation, so there is nothing pending to miss.

**Payload.** A flat list of rides carrying what both client-side consumers need — the
marker fields from `spots.json` and the ride-card fields from `rides/by-spot/<sid>.json`:

```
{d, id, spot_id, lat, lon, dest_lat, dest_lon, rating, wait, distance,
 comment, hitchhiker_name, submission_time, ride_datetime, arrival_datetime}
```

`spot_id` is `generate_spot_id(lat, lon)` — `lat.toFixed(5)_lon.toFixed(5)` — so it lines
up with the per-spot filenames and with the id `map.js` derives from marker coordinates.

Rides hidden by reports (`get_reported_dtags` logic in `show.py`, and the owner-delete
`RideReport` row) must be excluded here too, or a reported ride would reappear for 10
minutes. Since the window only ever holds a handful of rides, filter by checking the
`ride_report` table for the returned `d` tags.

**Shared extraction.** Pulling `lat/lon/dest/wait/distance/hitchhiker_name` out of `stops`
and `hitchhikers` already exists twice: as scalar Python in `ride_detail` (`main.py:636`)
and as pandas in `show.py`. Extract the scalar version out of `ride_detail` into one helper
that both `ride_detail` and this endpoint call. Do not write a third copy.

In the steady state this endpoint returns `[]`; at most it returns the rides logged in the
last few minutes, so it needs no caching beyond the ordinary response.

### Part 3 — Merging pending rides into the map

`map.js` fetches `/pending_rides.json` after `loadMarkers`, exactly like
`loadProposedSpotMarkers`: non-blocking, silent on a failed/missing endpoint, never able to
break the map. Group the entries by `spot_id`, then:

- **Spot already has a marker** → increment its `_data.review_count`.
  Deliberately **do not** recompute the marker's rating/colour. `show.py`'s mean is taken
  over a filtered ride set (low-value rides — anonymous, no comment, no wait — are dropped
  from detail views but still counted in `review_count`), and that filter is not
  reproducible client-side. A wrong colour for 10 minutes is worse than a stale one; the
  count is exact, so only the count moves.
- **Brand-new spot (no marker)** → create a `circleMarker` the same way `loadMarkers` does,
  with `rating` = mean of the pending ratings and `review_count` = the group size, and add
  it to `markerCluster`. This is the case that today shows nothing at all.
- Keep the grouped rides in a module-scoped map keyed by `spot_id`.

`handleMarkerClick` then merges the pending rides for that spot into the list it fetched
from `rides/by-spot/<sid>.json`, **deduping on ride `id`** — both sources carry the Nostr
event id, so the overlap window (file regenerated, endpoint not yet re-fetched) renders
each ride once. The existing sort by `submission_time` puts the fresh ride at the top. A
spot whose per-spot file 404s (brand-new spot) still renders its single ride, since the
404 branch already leaves `spotRides` empty rather than failing.

This covers the `/spot/<spot_id>` permalink case for free: that route renders the same
`map.html` and the pane is built by the same code path.

### Part 4 — Share link and ride-page OpenGraph tags

`static/share_card.js:461` shares `/spot/<spot_id>` and says why: "The ride has no
permalink yet — it only gets one once the Nostr fetch cron ingests it (`/ride/<d_tag>`
404s until then)". Part 1 removes that reason.

- The submit redirect becomes `/?ride=<d_tag>#success` (all three variants: `#success`,
  `#success-anon`, `#success-invite`).
- `map.js` reads the `ride` query param and passes it into `hmShareCard.build`.
- `hmShareCard.build` uses `window.location.origin + "/ride/" + d_tag` when a `d` tag is
  supplied, and keeps the spot URL as the fallback when it is not — the offline outbox
  submits over `fetch` and never navigates, and a returning visitor can run new `map.js`
  against a service-worker-cached older page. The stale comment is replaced.
- The `hmLastRide` sessionStorage stash in `ride_form.html` is unchanged; the `d` tag
  cannot come from there (it does not exist until the server publishes), which is why it
  travels in the redirect URL.

`templates/ride_detail.html` gains `og_title` / `og_description` overrides (the blocks
already exist in `base.html`; `ride_detail.html` currently overrides neither). Content from
data the route already computes: rating, distance, wait, comment excerpt, and the spot's
display name. For the name, read `spot.name` from `dist/rides/by-spot/<sid>.json` when that
file exists — that is the fully-cascaded name the map itself shows — and fall back to the
`spot_name` table, then to bare coordinates. Text tags only; no `og:image`.

## Files touched

| File | Change |
|---|---|
| `hitch/blueprints/utils/post_hitchhiking_ride_to_nostr.py` | `post()` also exposes the signed `Event` |
| `hitch/blueprints/main.py` | Upsert the event into `ride_event` after publishing; `/pending_rides.json`; extract the shared scalar ride-field helper out of `ride_detail`; `?ride=<d_tag>` in the redirects; OG values for `ride_detail` |
| `hitch/scripts/show.py` | Capture the pre-`read_sql` timestamp; write `dist/generated_at.json` last |
| `hitch/static/map.js` | Fetch and merge `/pending_rides.json` (markers + `handleMarkerClick` dedupe); read `?ride=` and hand the `d` tag to the share card |
| `hitch/static/share_card.js` | Prefer `/ride/<d_tag>` as the share URL; drop the stale comment |
| `hitch/templates/ride_detail.html` | `og_title` / `og_description` blocks |

## Testing

- **Unit, `parse_post_to_ride_fields` round trip:** a signed `Event` from the poster →
  `to_dict()` → parsed fields produce a valid `RideEvent`, and re-parsing the same event
  yields identical column values (the property the upsert's `unchanged` branch relies on).
- **Unit, upsert semantics:** insert; re-apply the same event → unchanged. Apply an edit
  (same `pubkey`/`d`, newer `created_at`, new `id`) → the row is overwritten including its
  primary key, and there is still exactly one row for that coordinate.
- **Route, `/ride/<d_tag>`:** 404 before submit, 200 immediately after, and the page shows
  the submitted rating/comment.
- **Route, `/pending_rides.json`:** `[]` when `generated_at.json` is newer than every ride;
  contains the ride when it is older; excludes an owner-deleted / reported ride; falls back
  to the `rides_index.json` mtime when `generated_at.json` is absent.
- **Publish-failure isolation:** a DB error at the insert site does not change the
  submit response (still a redirect / `{"ok": true}`).
- **Frontend:** no headless browser on prod (per CLAUDE.md). Verify the merge and dedupe
  helpers under `node` by stubbing `window`/`document`/`fetch` and exercising them against
  a fixture pending list plus a fixture per-spot file; verify the full click-through in a
  browser on a dev machine or by asking the user to check.
- **End to end, manual:** log a ride → the success card's share link is `/ride/<d_tag>` and
  resolves → reload the map, the marker's count is up and the ride is top of the spot pane
  → wait for the cron and confirm no duplicate ride card and no double-counted marker.

## Deployment notes

- `hitch/scripts/show.py` is baked into the image (`hitch/scripts/` is not bind-mounted),
  so the `generated_at.json` change needs an image rebuild. Until it lands, the endpoint
  runs on the `rides_index.json` mtime fallback, which is safe.
- `hitch/templates/ride_detail.html` is mounted but cached — `sudo docker restart
  hitchhiking-map` is required for the OG tags to appear.
- `hitch/static/*.js` is mounted and picked up live; `asset_url()` re-hashes on the next
  render. Note the half-applied window this creates: the JS change goes live before the
  template change does.
- No new columns, so no manual SQLite migration.
