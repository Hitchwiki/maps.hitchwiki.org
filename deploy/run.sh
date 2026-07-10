# Get rides from Nostr once initially and compile TS scripts
cd /app/hitch/scripts/fetch_hitchhiking_events
# npm ci installs exactly what package-lock.json pins, so the versions we audited
# are the versions that run; npm install may silently resolve newer in-range ones.
npm ci --no-fund
npx tsc

cd /app

flask init
service cron start

# Waitress, not `flask run`: Werkzeug's dev server has no bounded thread pool and no
# protection against slow or malformed clients. Apache terminates TLS and proxies here.
# 16 threads, not waitress's default 4: every map load pulls several MB of dist/ JSON
# through catch_all(), and a worker is held for the whole file read. The work is file
# I/O (releases the GIL), so threads parallelise past the 4 cores; slow clients cost
# nothing here, as waitress writes responses from its single select loop, not a worker.
waitress-serve --host=0.0.0.0 --port=4242 --threads=16 --call hitch:create_app