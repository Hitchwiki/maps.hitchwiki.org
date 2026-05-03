# Get rides from Nostr once initially and compile TS scripts
cd /app/hitch/scripts/fetch_hitchhiking_events
npm install --no-fund
npx tsc

cd /app

flask init
service cron start
export FLASK_RUN_PORT=4242
flask run --host=0.0.0.0 --port=4242