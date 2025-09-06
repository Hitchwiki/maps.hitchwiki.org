# Get rides from Nostr once initially and compile TS scripts
cd /app/hitch/scripts/fetch_hitchhiking_events
npm install
npx tsc

cd /app

flask init
service cron start
flask run --host=0.0.0.0 --port=5000