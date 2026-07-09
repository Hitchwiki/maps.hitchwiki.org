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
waitress-serve --host=0.0.0.0 --port=4242 --threads=4 --call hitch:create_app