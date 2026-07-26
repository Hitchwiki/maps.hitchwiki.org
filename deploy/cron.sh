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
# every Monday at 00:50 — FULL Nostr fetch (delete-and-recreate). The incremental job now
# handles deletions too, so this is only needed to (a) catch back-dated events an incremental
# `since` query skips, and (b) regenerate the public dist/allPosts.json / allPosts.csv exports.
# Runs weekly, a few hours before the Monday 08:00 Hugging Face dataset push that reads
# allPosts.json, so that export is always fresh for the push.
50 0 * * 1 cd /app && /usr/bin/flock -n /tmp/fetch_nostr.lockfile bash -c 'echo "=== $(date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ) ===" && /usr/local/bin/flask --app hitch generate fetch_nostr' > logs/fetch_nostr_full.log 2>&1
# every 10 minutes
*/10 * * * * cd /app && /usr/bin/flock -n /tmp/show.lockfile bash -c 'echo "=== $(date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ) ===" && /usr/local/bin/flask --app hitch generate show' > logs/show.log 2>&1

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
# every day at 5 AM
0 5 * * * cd /app && /usr/bin/flock -n /tmp/dashboard.lockfile bash -c 'echo "=== $(date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ) ===" && /usr/local/bin/flask --app hitch generate dashboard' > logs/dashboard.log 2>&1
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
# last access, so a route still being shared after 7 days is simply rebuilt once. The shared
# OSM tile cache (dist/tiles) is deliberately kept forever and is NOT touched here.
30 1 * * * find /app/dist/dir -type f -mtime +7 -delete > logs/prune_dir_previews.log 2>&1

# every day at 00:30 — remind signed-up users who still have zero logged rides (7- and 30-day nudge)
30 0 * * * cd /app && /usr/bin/flock -n /tmp/remind_inactive_users.lockfile bash -c 'echo "=== $(date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ) ===" && /usr/local/bin/flask --app hitch generate remind_inactive_users' > logs/remind_inactive_users.log 2>&1
