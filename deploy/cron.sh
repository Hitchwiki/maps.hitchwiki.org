# @reboot cd hitch && screen -d -m bash -c '. $HOME/.bashrc; /usr/local/bin/waitress-serve server:app; bash'
# every 30 minutes
*/30 * * * * cd /app && /usr/bin/flock -n /tmp/fetch_nostr.lockfile bash -c 'echo "=== $(date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ) ===" && /usr/local/bin/flask --app hitch generate fetch_nostr' > logs/fetch_nostr.log 2>&1
# every 10 minutes
*/10 * * * * cd /app && /usr/bin/flock -n /tmp/show.lockfile bash -c 'echo "=== $(date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ) ===" && /usr/local/bin/flask --app hitch generate show' > logs/show.log 2>&1

# daily at 4:45 AM — reverse-geocode new rides' endpoints into the ride_place table.
# Incremental: steady-state runs geocode nothing, so reverse_geocoder never builds its
# ~150 MB index. Offline by design — that cost must never live in the web workers.
45 4 * * * cd /app && /usr/bin/flock -n /tmp/ride_places.lockfile bash -c 'echo "=== $(date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ) ===" && /usr/local/bin/flask --app hitch generate ride_places' > logs/ride_places.log 2>&1
# every day at 2 AM
0 7 * * * cd /app && /usr/bin/flock -n /tmp/sync_upstream.lockfile bash -c 'echo "=== $(date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ) ===" && /usr/local/bin/flask --app hitch generate sync_upstream' > logs/sync_upstream.log 2>&1
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
# every day at 5 AM
0 5 * * * cd /app && /usr/bin/flock -n /tmp/dashboard.lockfile bash -c 'echo "=== $(date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ) ===" && /usr/local/bin/flask --app hitch generate dashboard' > logs/dashboard.log 2>&1
# every day at 6 AM
0 6 * * * cd /app && /usr/bin/flock -n /tmp/cities.lockfile bash -c 'echo "=== $(date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ) ===" && /usr/local/bin/flask --app hitch generate cities' > logs/cities.log 2>&1
# every Monday at 8 AM
0 8 * * 1 cd /app && /usr/bin/flock -n /tmp/sync_hitchhiking_rides_dataset.lockfile bash -c 'echo "=== $(date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ) ===" && /usr/local/bin/flask --app hitch generate sync_hitchhiking_rides_dataset' > logs/sync_hitchhiking_rides_dataset.log 2>&1
# first of every month at 9 AM — regenerate country hitchability CSV + country_ratings.json / country_insights.json
0 9 1 * * cd /app && /usr/bin/flock -n /tmp/country_ratings.lockfile bash -c 'echo "=== $(date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ) ===" && /usr/local/bin/flask --app hitch generate country_ratings' > logs/country_ratings.log 2>&1
# every day at midnight
0 0 * * * cd /app && /usr/bin/flock -n /tmp/notify_nearby_hitchhikers.lockfile bash -c 'echo "=== $(date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ) ===" && /usr/local/bin/flask --app hitch generate notify_nearby_hitchhikers' > logs/notify_nearby_hitchhikers.log 2>&1
