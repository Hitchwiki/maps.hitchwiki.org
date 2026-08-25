# @reboot cd hitch && screen -d -m bash -c '. $HOME/.bashrc; /usr/local/bin/waitress-serve server:app; bash'
# every 5 minutes — INCREMENTAL Nostr fetch. Asks the relay only for events newer than the
# newest ride we already hold and upserts them (keyed on the addressable (pubkey, d)), instead
# of re-fetching + re-serialising the whole 75k-event / 100+ MB history every run. Because it's
# sub-second in steady state (a since-query returning ~0 rides + a few hundred tiny kind-5
# events) it can run far more often than the old full fetch, which pinned a CPU core for a
# minute+ and could only be afforded every 30 min. Also fetches all kind-5 (NIP-09) deletion
# events and removes the referenced rides (author-pubkey checked), so a deleted ride disappears
# within ~5 min, not a week. Shares fetch_nostr.lockfile with the weekly full job (flock -n) so
# the two never overlap — if a 5-min tick lands during the weekly full run it simply skips.
*/5 * * * * cd /app && /usr/bin/flock -n /tmp/fetch_nostr.lockfile bash -c 'echo "=== $(date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ) ===" && /usr/local/bin/flask --app hitch generate fetch_nostr_incremental' > logs/fetch_nostr.log 2>&1
# every Monday at 00:51 — FULL Nostr fetch (delete-and-recreate). The incremental job now
# handles deletions too, so this is only needed to (a) catch back-dated events an incremental
# `since` query skips, and (b) regenerate the public dist/allPosts.json / allPosts.csv exports.
# Runs weekly, a few hours before the Monday 08:00 Hugging Face dataset push that reads
# allPosts.json, so that export is always fresh for the push.
# The minute MUST NOT be a multiple of 5. This was 00:50, which cron starts in the same second
# as the */5 incremental tick above; they share fetch_nostr.lockfile, so whichever loses the
# race dies to `flock -n` — and it was always this one. The job silently never ran between
# 2026-07-19 and 2026-07-30 (its log is 0 bytes: flock exits before even the echo), during which
# 3598 back-dated rides accumulated unfetched and allPosts.json went 11 days stale. :51 leaves
# the ~2 s incremental finished and the lock free.
51 0 * * 1 cd /app && /usr/bin/flock -n /tmp/fetch_nostr.lockfile bash -c 'echo "=== $(date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ) ===" && /usr/local/bin/flask --app hitch generate fetch_nostr' > logs/fetch_nostr_full.log 2>&1
# Every 30 minutes, not every 10. A run that actually regenerates takes 215-385 s and
# peaks ~1.5 GB, so a */10 schedule spent much of every hour holding the largest allocation
# on this host and repeatedly lost `flock -n` to its own previous run (show_ram.log had a
# 4-hour hole on 2026-08-07 from exactly that). Freshness barely moves: a new ride is
# already visible immediately via /pending_rides.json, which serves rides newer than the
# last snapshot, so this only decides when the generated files catch up.
*/30 * * * * cd /app && /usr/bin/flock -n /tmp/show.lockfile bash -c 'echo "=== $(date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ) ===" && /usr/local/bin/flask --app hitch generate show' > logs/show.log 2>&1

# daily at 4:45 AM — reverse-geocode new rides' endpoints into the ride_place table.
# Incremental: steady-state runs geocode nothing, so reverse_geocoder never builds its
# ~150 MB index. Offline by design — that cost must never live in the web workers.
45 4 * * * cd /app && /usr/bin/flock -n /tmp/ride_places.lockfile bash -c 'echo "=== $(date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ) ===" && /usr/local/bin/flask --app hitch generate ride_places' > logs/ride_places.log 2>&1
# each day at midnight
# 0 0 * * * cd /app && /usr/bin/flock -n /tmp/dump.lockfile bash -c '. $HOME/.bashrc; /usr/local/bin/python flask --app hitch generate dump' > logs/dump.log 2>&1
# each day at 3
# 0 3 * * * cd /app && /usr/bin/flock -n /tmp/dashboard.lockfile bash -c '. $HOME/.bashrc; /usr/local/bin/python flask --app hitch generate fetch-roads' > logs/fetchroad.log 2>&1
# each day at midnight
# 0 0 * * * cd /app && /usr/bin/flock -n /tmp/dashboard.lockfile bash -c '. $HOME/.bashrc; /usr/local/bin/python flask --app hitch generate fetch-areas' > logs/fetcharea.log 2>&1
# every day at 2 AM — rebuild the routing graph (dist/repeatable_routes.json).
# Standalone script, not a `flask generate` one. --skip-detailed omits the 48 MB
# ride_routes.json, which nothing serves. OSRM routes are cached in
# dist/route_cache.jsonl, so a daily run only fetches the endpoints of rides
# added since yesterday. Runs at night because the spatial join over ~22k rides
# is the heaviest job on this OOM-prone host; it reads dist/spots.json, which the
# 10-minute `show` job keeps fresh.
0 2 * * * cd /app && /usr/bin/flock -n /tmp/build_ride_routes.lockfile bash -c 'echo "=== $(date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ) ===" && /usr/local/bin/python3 /app/hitch/scripts/build_ride_routes.py --skip-detailed' > logs/build_ride_routes.log 2>&1
# every day at 3 AM
0 3 * * * cd /app && /usr/bin/flock -n /tmp/sync_osm.lockfile bash -c 'echo "=== $(date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ) ===" && /usr/local/bin/flask --app hitch generate sync_osm' > logs/sync_osm.log 2>&1
# every day at 4 AM
0 4 * * * cd /app && /usr/bin/flock -n /tmp/sync_hitchwiki.lockfile bash -c 'echo "=== $(date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ) ===" && /usr/local/bin/flask --app hitch generate sync_hitchwiki' > logs/sync_hitchwiki.log 2>&1
# every day at 4:15 AM — pull Hitchwiki Category:Event pages into dist/events.json
15 4 * * * cd /app && /usr/bin/flock -n /tmp/sync_events.lockfile bash -c 'echo "=== $(date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ) ===" && /usr/local/bin/flask --app hitch generate sync_events' > logs/sync_events.log 2>&1
# every day at 3:30 AM
30 3 * * * cd /app && /usr/bin/flock -n /tmp/sync_car_pooling.lockfile bash -c 'echo "=== $(date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ) ===" && /usr/local/bin/flask --app hitch generate sync_car_pooling' > logs/sync_car_pooling.log 2>&1
# every day at 3:45 AM
45 3 * * * cd /app && /usr/bin/flock -n /tmp/sync_fuel.lockfile bash -c 'echo "=== $(date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ) ===" && /usr/local/bin/flask --app hitch generate sync_fuel' > logs/sync_fuel.log 2>&1
# every day at 4:30 AM — reverse-geocode street names for spots no OSM feature can name.
# Standalone script, not a `flask generate` one. Reads dist/spots.json, so it must run
# after `show`; capped at 2000 geocodes (~33 min at the 1 req/s we hold ourselves to
# against Photon) so a nightly run stays bounded. The initial ~30k backlog is drained by
# a manual `--limit 0` run, after which only newly created spots are left.
30 4 * * * cd /app && /usr/bin/flock -n /tmp/spot_names.lockfile bash -c 'echo "=== $(date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ) ===" && /usr/local/bin/python3 /app/hitch/scripts/spot_names.py' > logs/spot_names.log 2>&1
# every day at 4:50 AM — split dist/spots.gpx into one GPX per country (issue #114).
# Standalone script, not folded into the 10-minute `show` cycle: country data only
# changes when new spots appear, so re-splitting ~190 countries' worth of GPX every
# 10 minutes would add real, unnecessary I/O to that already runtime-sensitive job.
# Reads dist/spots.json and dist/rides/by-spot/<id>.json, so it must run after `show`
# (always fresh) and after `spot_names` (4:30, ~33 min cap in steady state well under
# 20 min once the initial backlog is drained), so spots carry real names, not bare
# coordinates.
50 4 * * * cd /app && /usr/bin/flock -n /tmp/spots_by_country.lockfile bash -c 'echo "=== $(date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ) ===" && /usr/local/bin/flask --app hitch generate spots_by_country' > logs/spots_by_country.log 2>&1
# every day at 5:30 AM — "Hitchhiking from X to Y" SEO pages for well-evidenced city pairs.
# Runs BEFORE cities (6 AM) on purpose: cities.py writes sitemap.xml at the end of its run
# and picks up dist/route/index.json, so a route page generated now is advertised the same
# night rather than a day later. It reads dist/city/top_cities.json from the PREVIOUS cities
# run (a day-old ride ranking is fine) and dist/repeatable_routes.json from the 2 AM routing
# rebuild. Builds the ~190 MB routing graph once for the whole batch — never in a web worker.
30 5 * * * cd /app && /usr/bin/flock -n /tmp/route_pages.lockfile bash -c 'echo "=== $(date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ) ===" && /usr/local/bin/flask --app hitch generate route_pages' > logs/route_pages.log 2>&1
# every day at 6 AM
0 6 * * * cd /app && /usr/bin/flock -n /tmp/cities.lockfile bash -c 'echo "=== $(date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ) ===" && /usr/local/bin/flask --app hitch generate cities' > logs/cities.log 2>&1
# every Sunday at 1 AM — off-site backup of the SQLite DB to Google Drive, PII scrubbed.
# Standalone script, not a `flask generate` one. Runs before the 2 AM routing rebuild so the
# two heaviest jobs on this OOM-prone host don't overlap: the backup holds a full ~400 MB
# snapshot plus its gzip on disk. Emails are replaced with placeholders and 2FA secrets /
# phone numbers / login IPs are dropped before anything leaves the host.
0 1 * * 0 cd /app && /usr/bin/flock -n /tmp/backup_to_drive.lockfile bash -c 'echo "=== $(date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ) ===" && /usr/local/bin/python3 /app/hitch/scripts/backup_to_drive.py' > logs/backup_to_drive.log 2>&1
# every Monday at 7 AM — rebuild /why-not-hitchhike (dist/why_not_hitchhike.json).
# Weekly rather than nightly because the output only moves when a *new* ride arrives
# carrying a departure time, a destination AND a waiting time together — a few dozen a
# week out of ~74k rides, so a daily run would recompute an identical file six times.
# Reads dist/rides_index.json for canonical spot ids, so it must run after `show` (every
# 10 min, always fresh), and after ride_places (4:45) / spot_names (4:30) so new spots and
# destinations are already named. 7 AM leaves the 6 AM cities run finished.
0 7 * * 1 cd /app && /usr/bin/flock -n /tmp/why_not_hitchhike.lockfile bash -c 'echo "=== $(date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ) ===" && /usr/local/bin/flask --app hitch generate why_not_hitchhike' > logs/why_not_hitchhike.log 2>&1
# daily at 7:20 AM — rebuild /statistics after the overnight fetch/generation jobs.
# The page reads this small aggregate rather than scanning every ride's JSON blobs in a
# web worker. Daily is cheap and makes newly logged group/gender combinations visible.
20 7 * * * cd /app && /usr/bin/flock -n /tmp/wait_statistics.lockfile bash -c 'echo "=== $(date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ) ===" && /usr/local/bin/flask --app hitch generate wait_statistics' > logs/wait_statistics.log 2>&1
# daily at 7:25 AM — rebuild the small weekly ride/source aggregate.
25 7 * * * cd /app && /usr/bin/flock -n /tmp/ride_collection_statistics.lockfile bash -c 'echo "=== $(date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ) ===" && /usr/local/bin/flask --app hitch generate ride_collection_statistics' > logs/ride_collection_statistics.log 2>&1
# every Monday at 8 AM
0 8 * * 1 cd /app && /usr/bin/flock -n /tmp/sync_hitchhiking_rides_dataset.lockfile bash -c 'echo "=== $(date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ) ===" && /usr/local/bin/flask --app hitch generate sync_hitchhiking_rides_dataset' > logs/sync_hitchhiking_rides_dataset.log 2>&1
# first of every month at 9 AM — regenerate country hitchability CSV + country_ratings.json / country_insights.json
0 9 1 * * cd /app && /usr/bin/flock -n /tmp/country_ratings.lockfile bash -c 'echo "=== $(date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ) ===" && /usr/local/bin/flask --app hitch generate country_ratings' > logs/country_ratings.log 2>&1
# every day at midnight
0 0 * * * cd /app && /usr/bin/flock -n /tmp/notify_nearby_hitchhikers.lockfile bash -c 'echo "=== $(date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ) ===" && /usr/local/bin/flask --app hitch generate notify_nearby_hitchhikers' > logs/notify_nearby_hitchhikers.log 2>&1

# every day at 1:30 AM — prune the route link-preview cache (dist/dir). It's a pure cache:
# any /dir/<from>/<to> hit regenerates its .json/.png pair on demand (~4-7 s cold), and the
# URL space is quadratic in coordinates — crawlers can mint new keys forever — so without a
# sweep the directory grows unbounded (~2 MB/day observed). mtime is generation time, not
# last access, so a route still being shared after 7 days is simply rebuilt once.
30 1 * * * find /app/dist/dir -type f -mtime +7 -delete > logs/prune_dir_previews.log 2>&1

# every day at 1:45 AM — prune the shared OSM tile cache (dist/tiles). Was "kept forever" by
# design (a given tile is fetched at most once, and the same tiles are reused across many
# routes) until the maps.hitchwiki.org outage of 2026-08-22: nothing bounds how many *distinct*
# routes get previewed, so a crawler hitting many /dir/<a>/<b> links (the URL space is quadratic,
# same as dist/dir above) grows this cache with no ceiling at all -- unlike dist/dir, which at
# least always cleared itself every 7 days. route_preview.py's fetch_tile() now bumps a tile's
# mtime on every cache hit, so this sweep reads as "not requested by any preview in 90 days",
# not "fetched more than 90 days ago" -- a tile behind a route people keep sharing never ages
# out; only genuinely one-off crawler traffic does.
45 1 * * * find /app/dist/tiles -type f -mtime +90 -delete > logs/prune_tiles.log 2>&1

# every day at 00:30 — remind signed-up users who still have zero logged rides (7- and 30-day nudge)
30 0 * * * cd /app && /usr/bin/flock -n /tmp/remind_inactive_users.lockfile bash -c 'echo "=== $(date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ) ===" && /usr/local/bin/flask --app hitch generate remind_inactive_users' > logs/remind_inactive_users.log 2>&1
