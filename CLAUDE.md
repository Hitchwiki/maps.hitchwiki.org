# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Environment Setup
- **Virtual Environment**: `python3 -m venv .venv && source .venv/bin/activate`
- **Install Dependencies**: `pip install -r requirements.txt`
- **Fix DB permissions**: The downloaded database is often owned by root. Run `sudo chown $USER:$USER db/hitchhiking-prod.sqlite` (and/or `db/hitchhiking.sqlite`) to make it writable, otherwise Flask will crash with `sqlite3.OperationalError: attempt to write a readonly database` on any write operation (e.g. user registration).
- **Configuration**: `cp example.env .env` (then set missing env variables)

### Flask Commands
- **Initialize Database**: `flask init` - Creates tables and default roles, runs generate-all
- **Run Server**: `flask run` - Starts development server
- **Execute Script**: `flask generate <script_name>` - Runs scripts from hitch/scripts/
- **Run All Scripts**: `flask generate-all` - Runs the scripts needed to populate `dist/` on first boot, only if their output doesn't already exist (cron keeps them fresh afterwards): `fetch_nostr`, `sync_osm`, `sync_car_pooling`, `sync_hitchwiki`, `show`, `dashboard`, `cities`. Most are gated on `ENVIRONMENT == "prod"`; only `show` and `dashboard` run in dev (see `hitch/__init__.py`)

## Coding Conventions

- **Requirement comments**: Add a comment above non-obvious logic explaining the requirement it implements (the "why"), not just the "what". This is especially important for business rules, edge cases, and multi-step operations.

### Code Quality
- **Linting**: `ruff check` - Code linting with line length 130
- **Formatting**: `ruff format` - Auto-format code
- **Pre-commit**: Uses ruff for linting and formatting via pre-commit hooks

### Testing
- **Run Tests**: `python -m pytest tests/ -v`

## Architecture Overview

### Core Structure
- **Flask Application**: Main app factory in `hitch/__init__.py` with blueprint registration
- **Database Models**: SQLAlchemy models in `hitch/models.py` including User, RideEvent, OsmHitchhikingSpot
- **Blueprints** (registered in `register_blueprints`, `hitch/__init__.py`):
  - `oauth` - Hitchwiki OAuth2 login flow
  - `main` - Map rendering, experience logging, ride submission
  - `user` - User management and authentication
  - Note: `hitch/blueprints/publish_ride.py` is an example/utility module showing how to transform a ride into the standard and post it to Nostr — it is **not** a registered Flask blueprint despite its filename/location.
- **Extensions**: Flask-Security for auth, Flask-SQLAlchemy for DB, Flask-Mailman for email

### Map URL scheme
Modelled on OpenStreetMap's `/node/<id>#map=<zoom>/<lat>/<lon>`. Two independent pieces of state:

| Part | Carries | Example |
|---|---|---|
| Path | Which spot is selected (identity) | `/spot/51.08170_13.73629` |
| Path | Which route is planned (identity) | `/dir/47.55811,7.58783/52.51739,13.39513` |
| Hash | Where the camera is (viewport) | `#map=18/51.08170/13.73629` |

- **Identity in the path, not the fragment.** Several messengers strip the `#fragment` when auto-linking a pasted URL, which is why spot coordinates previously lived in `?lat=&lon=`. A path survives; the viewport hash is the part that's harmless to lose.
- **The spot id is `generate_spot_id()`** (`show.py`): `lat.toFixed(5)_lon.toFixed(5)`. Same id as the `dist/rides/by-spot/<spot_id>.json` filename, so a permalink and its detail file always agree. 5 decimals (~1.1 m) is finer than the 5 m merge radius, so distinct spots never collide.
- **`/spot/<spot_id>`** (`main.py`, `render_spot`) renders the same `map.html` as `/` — the spot pane still opens client-side. The route exists so the URL survives a round trip, and so the page can emit per-spot OpenGraph tags (title/description/canonical) built from the per-spot JSON file. Any well-formed coordinate returns 200, so pages with no ride data get `<meta name="robots" content="noindex">` to avoid an unbounded space of indexable soft-404s.
- **`/dir/<slat>,<slon>/<dlat>,<dlon>`** (`main.py`, `render_directions`) is the shareable route link, written by `routing.js` (`updateShareUrl`) and reopened by `openFromUrl`. It replaced the old `#dir/…` fragment for the reason above *and* because a fragment never reaches the server, so it could never carry a link preview. The legacy hash is still accepted and rewritten to this path. Always `noindex`: the space of coordinate pairs is the square of the spot space.
  - Preview assets are built by `hitch/scripts/route_preview.py` into `dist/dir/<key>.{json,png}` (OG title/description + a 600x315 OSM basemap with the route drawn on it), and served by `render_directions_preview`. Generation runs in a **subprocess**, single-flighted by a `<key>.json.lock` file: the routing graph costs ~190 MB and ~3 s to build, which must not live in the waitress workers on this OOM-prone host. Stale locks (killed builder) are reclaimed after `2 * PREVIEW_TIMEOUT_S`. Cold hit ≈ 4-7 s; afterwards it's a file read. OSM tiles are cached forever under `dist/tiles/<z>/<x>/<y>.png`, so each tile is fetched at most once.
  - The route facts come from `hitch/scripts/repeatable_router.py` (the Python twin of `static/routing.js` — keep them numerically identical), and the endpoint labels from Photon reverse geocoding, preferring its `city` field over `name` (which is otherwise the nearest street or POI). `reverse_geocoder` is the offline fallback.
- **The viewport hash is rewritten on `moveend` via `replaceState`**, never `pushState` — a pan is not a navigation. `updateMapHash()` refuses to touch the hash when it holds navigation state (`#menu`, `#routing`, `#country/<name>`, `#insights`, `#dir/…`).
- **Legacy `?lat=&lon=` and `#lat,lon` links still resolve** and are rewritten in place to the canonical path (`setSpotUrl` → `replaceState`, since canonicalising is not a navigation and `pushState` would make the back button bounce onto a URL that reopens the same spot).
- Coordinate precision in the hash follows OSM's `zoomPrecision` (`ceil(log(zoom)/LN2)`), so shared links stay short at low zoom. This only affects the map centre, never spot identity.
- `sw.js` normalises `/spot/<id>` and `/dir/<from>/<to>` to `/` in its cache key: both render the same template (only the OG tags differ, and crawlers don't run the service worker), so they share one cached copy and work offline.

### Key Models
`hitch/models.py` defines ~15 models; the most relevant:
- **RideEvent**: Stores Nostr ride events with JSON content and extracted columns
- **OsmHitchhikingSpot** / **OsmCarPoolingSpot**: OpenStreetMap hitchhiking / car-pooling spot locations
- **HitchwikiArticleLocation** / **HitchwikiArticleMap**: Hitchwiki article coordinates and embedded map views
- **CoHitchhiker**: Co-hitchhiker acceptance tracking
- **User** / **Role**: Flask-Security accounts and roles
- **Follow** / **Notification**: User following and notifications
- **Trip** / **TripRide**: Trips grouping multiple rides
- **RideReport**: User-reported issues on rides
- **ServiceArea** / **RoadIsland** / **RoutingSearch**: Routing-support data

### Data Processing Scripts (hitch/scripts/)
- **fetch_nostr.py**: Fetches ride data from Nostr relays (runs every 30min via cron)
- **show.py**: Generates map data views (runs every 10min via cron)
- **dashboard.py**: Analytics dashboard generation (daily)
- **cities.py**: Per-city page generation (daily)
- **dump.py**: Database export functionality
- **sync_osm.py**: OSM hitchhiking-spot synchronization (fetches highway=hitchhiking spots, daily)
- **sync_car_pooling.py**: OSM car-pooling spot synchronization (daily)
- **sync_fuel.py**: OSM fuel / gas station synchronization (`amenity=fuel`, daily at 3:45 AM). A *global* fuel query is far too large for the public Overpass servers (hundreds of thousands of elements → reliable 504), and fuel is only used to flag hitchhiking spots that sit *at* a gas station (`show.py`, 100 m match, the `fuel` flag in `spots.json` / `fuel` field in per-spot files). So the script reads spot coordinates from the already-generated `dist/spots.json`, reduces them to 1° tiles, and queries Overpass for fuel only inside those tiles — batched ~60 bboxes per union request with 429/504 retry-and-backoff. **Depends on `spots.json` existing, so it must run after `show`.** `show.py` uses a spatial grid (0.01° cells) for the nearby-fuel lookup because the fuel set dwarfs the car-pooling/official-spot sets.
- **sync_hitchwiki.py**: Hitchwiki article synchronization (extracts coordinates from wiki articles, daily)
- **sync_events.py**: Hitchwiki events synchronization. Pulls every page in `Category:Events`, extracts each `{{Event|name|start|end|lat|lon}}` template, keeps events whose end date is today or later, and writes `dist/events.json` directly (self-contained → no DB model, like `country_ratings`). The map draws a calendar-pin marker per event; clicking it opens a bottom sheet with the name, dates, a plain-text blurb from the wiki page, and a Hitchwiki link (daily at 4:15 AM). Note: Hitchwiki is behind Cloudflare, which 403s ("Just a moment…") requests without a browser-like `User-Agent`, so the script sends one.
- **build_ride_routes.py**: Builds the routing graph from rides (daily at 2 AM). For every ride with a destination it fetches an OSRM driving route and records which *other* known start spots lie within 300 m of the polyline, in travel order; sequences shared by ≥2 rides become the "repeatable" trees in `dist/repeatable_routes.json` (read by `static/routing.js`). The same run also writes `dist/oneoff_routes.json` — the identical trees with the ≥2 threshold dropped to 1 (so a corridor a single ride established still forms edges), indexing the *same* `spots` array and carrying a `spot_count` guard. The routers fetch/build it lazily and search it **only when the repeatable graph connects nothing** (`routing.js` `loadFallbackRouter` / `repeatable_router.py` `load_oneoff_router`); it's a ~6× larger superset (~3.4 MB), so it must not load on every map view. Routes that use a support-1 leg are flagged in the UI ("1 logged ride"). Standalone script (plain `python3`, not `flask generate`), reads SQLite directly. OSRM responses are cached in `dist/route_cache.jsonl` (~675 MB, read via a byte-offset index so geometries never all sit in RAM), so a daily run only fetches routes for rides added since the last run. Spot consolidation must stay identical to `show.py`'s (5 m merge → service-area/road-island polygon grouping → snap onto `dist/spots.json`), otherwise routes reference phantom spots with no map marker.
- **sync_upstream.py**: Legacy hitchmap.com data sync (daily at 7 AM)
- **backup_to_drive.py**: Weekly off-site backup of the SQLite DB to Google Drive with PII scrubbed (Sundays at 1 AM). Standalone script (plain `python3`, stdlib only, no app context), not a `flask generate` one. Pipeline: online-backup-API snapshot (a plain `cp` of a live DB can capture a torn page) → scrub → `VACUUM` → gzip (~417 MB → ~99 MB, ~40 s) → `rclone copyto` → prune backups older than `BACKUP_RETENTION_DAYS` (28). **The `VACUUM` is part of the scrub, not an optimisation** — an `UPDATE` leaves the old email behind in freelist pages, recoverable from a file that looks clean via SQL. The scrub replaces `user.email` with `user<id>@example.invalid` (keyed by id because the column is UNIQUE; `.invalid` is RFC 2606 reserved so a restored backup can't mail a real person) and nulls `tf_totp_secret`, `us_totp_secrets`, `mf_recovery_codes`, `us_phone_number`, `tf_phone_number`, `last_login_ip`, `current_login_ip`. **`password` hashes are deliberately kept** so the backup can restore working logins; 2FA users would re-enrol. Note the scrub only covers the `user` table — ride comments sometimes contain emails hitchhikers typed in themselves, but that text is already public on the map. Config: `BACKUP_RCLONE_REMOTE` in `.env` plus `deploy/rclone.conf` (gitignored, generate per `deploy/rclone.conf.example`). The conf is mounted **read-write** because rclone writes refreshed OAuth tokens back to it — mounting it `:ro` yields a setup that works for an hour and then breaks. Test with `--no-upload` (optionally `--keep-local <path>`).
- **sync_hitchhiking_rides_dataset.py**: Push rides to the Hugging Face dataset (weekly)
- **notify_nearby_hitchhikers.py**: Email notifications for nearby hitchhikers (daily)
- **Destination enrichment (occasional manual batch jobs, NOT cron; both write inferred destinations to the `derived_ride_location` table, keyed by Nostr `d`, distinguished by the `kind` column; `show.py` + `build_ride_routes.py` merge these onto rides that reached Nostr with no destination).** Standalone scripts (plain `python3`), run against the root-owned prod DB via `sudo`:
  - **extract_destinations.py** (`kind=derived-comment-city`): mines the ride's free-text comment for the city it actually reached, geocodes it (`is_exact=0`, city centre). Three stages: `prefilter` (needs app context) → `extract` (LLM, needs `OPENAI_API_KEY`) → `geocode-store --db <path>`.
  - **derive_consecutive_destinations.py** (`kind=derived-consecutive-ride`): reconstructs trips a named user logged in one sitting — a run of their no-destination rides logged minutes apart with starts marching in one bearing forms a chain, so each ride's destination = the next ride's logged start (`is_exact=1`, a real spot). Run `--db <path> --dry-run` to preview chains, then without `--dry-run` to write; `ON CONFLICT DO NOTHING` never clobbers a comment-derived row. **After running either, regenerate map data + routing graph in the container** (`show --force`, then `build_ride_routes.py --skip-detailed`) so the new destinations reach the map and routes.
- Additional helpers: `fetch_osm_areas.py`, `fetch_osm_roads.py`, `sync_service_areas.py`, `sync_road_islands.py`, `routing.py`, `migrate.py`, `add-descriptions.py`

### Configuration
- **Environment-based**: BaseConfig + Development/Production/Testing configs in `hitch/settings.py`; selected via the `ENVIRONMENT` env var
- **Database**: SQLite with configurable paths via DATABASE_URI
- **Security**: Flask-Security with username-based auth, password hashing
- **Email**: Two paths — Flask-Mailman SMTP (defaults to SMTP2GO, `hitch/settings.py`) for Flask-Security mail, and SparkPost (`SPARKPOST_API_KEY` in `.env`) for welcome and nearby-hitchhiker emails (`hitch/blueprints/utils/send_welcome_email.py`, `send_nearby_hitchhikers_email.py`)

### Deployment
- **Docker**: Dockerfile and docker-compose.yml for containerization
- **Cron**: Automated data fetching via `deploy/cron.sh` with file locking
- **Static Files**: Served from dist/ directory, includes PWA manifest
- **Web Server**: Waitress for production, Apache/NGINX reverse proxy configs provided

## Debugging & Operations

### Do not install or run a headless browser on the prod server
Never install or use Playwright, Puppeteer, Chromium, or any other headless browser on the
**prod server** — not even via `npx`. It's an OOM-prone host (see the OOM section below), so a
browser download + Chromium process can tip it over. On a local dev machine this is fine —
install and use Playwright freely there to verify frontend behaviour.

When you can't run a browser (i.e. on prod), frontend behaviour (`map.js`, `routing.js`, …) must
be verified by reading the code, by running the pure-JS parts under `node`, or by asking the user
to check in their own browser. Node itself is fine: e.g. the routing engine in
`hitch/static/routing.js` can be exercised headlessly by stubbing `window`/`document`/`fetch` and
`eval`-ing the file, then calling `buildRouter`/`ensureWalk`/`alternatives` against
`dist/repeatable_routes.json`.

### Using Playwright on a local dev machine (visual/layout bugs)
For layout/overlap bugs you must actually render the page — reading CSS isn't enough (e.g. the
in-ride "Add details / In a ride / Finish Ride" overlap was a fixed-position status chip colliding
with the dock, invisible until measured). Workflow that works here:

1. **Install once:** `npm install -D playwright && npx playwright install chromium`. This creates
   `package.json` + `node_modules/` in the project root.
2. **Run driver scripts from `node`**, but they live in the scratchpad while Playwright is in the
   project's `node_modules`, so set `NODE_PATH`:
   `NODE_PATH=<project>/node_modules node myscript.js`.
3. **Serve the *edited* tree yourself — don't trust whatever is already on a port.** VS Code often
   runs its own Flask on **4243**, and the Docker container publishes **4242**; both may serve a
   *stale copy* of `hitch/static/*` (the container's baked image also 500s the map page on
   `asset_url is undefined`). Boot a fresh server from the project root on a free port and confirm
   it serves your change before testing:
   ```bash
   source .venv/bin/activate && FLASK_APP=hitch flask run --port 4245 --no-reload   # loads .env
   curl -s http://localhost:4245/static/inride.js | grep -c "<a string from your edit>"  # must be 1
   ```
   (`hitch` imports fine on the host here — the host venv is NOT minimal like prod's; `flask run`
   auto-loads `.env`, which a bare `python3 -c "import hitch"` does not, so it won't `RELAYS`-crash.)
4. **Drive UI state via the app's own JS, not by clicking through flows.** The in-ride journey is
   exposed as `window.inride = { journeyStore, journeyUI, journeyFlow, … }`; render the Finish dock
   directly with
   `journeyStore.set({state:'in-ride', gotRideMs:Date.now()-9e4, pickup:{lat,lon}, details:{}}); journeyUI.render(journeyStore.get())`.
5. **Measure, don't eyeball.** Use `getBoundingClientRect()` on each element and compute
   `max(0, min(a.bottom,b.bottom) - max(a.top,b.top))` for overlap; loop several mobile + laptop
   viewports (320→1440). Screenshot too, but the numbers are what confirm a fix.
6. **Clean up:** `pkill -f "flask run --port 4245"` when done. Leave `package.json`/`node_modules`
   only if the user wants Playwright kept around.

### Testing sync / generate scripts (run in the container, not the host venv)
On the prod server the host `.venv` is minimal (only a few packages like `requests`) — the full dependency set lives inside the `hitchhiking-map` Docker image, so `flask ... generate <script>` will `ModuleNotFoundError` on the host. Test scripts inside the running container instead:
```bash
sudo docker exec hitchhiking-map /usr/local/bin/flask --app hitch generate <script>
```
Only `dist/`, `hitch/static/`, `hitch/templates/`, `db/`, and `logs/` are bind-mounted into the container (see `docker inspect hitchhiking-map`). `hitch/scripts/` is **not** mounted — it's baked into the image at build time. So a new/edited script won't exist in the running container until the image is rebuilt; to test it before a rebuild, copy it in first:
```bash
sudo docker cp hitch/scripts/<script>.py hitchhiking-map:/app/hitch/scripts/<script>.py
```
Because `dist/`, `static/`, and `templates/` **are** mounted, changes to generated JSON, `map.js`, `style.css`, and `map.html` are picked up live without a rebuild; changes under `hitch/scripts/` and `deploy/cron.sh` require a rebuild/redeploy to take effect (including the cron entry that schedules the script).

### Finding errors for internal server errors (500s)
The app runs inside Docker. Flask tracebacks are NOT in the Apache logs — they go to the container's stdout/stderr. To get the real traceback:
```bash
sudo docker logs --tail 200 hitchhiking-map 2>&1 | grep -A 20 "Traceback\|Error\|500"
```
Apache only logs proxy-level errors (`Connection reset by peer`, `Connection refused`) which don't include the Python traceback. Always check Docker logs first when investigating 500s.

### Database migrations (adding columns)
There is no migration framework (no Alembic). When a new column is added to a model in `hitch/models.py`, the production SQLite database must be manually migrated — `flask init` / `db.create_all()` will NOT add columns to existing tables.

**When you add a column to a model, also run this against the production DB:**
```bash
sudo docker exec hitchhiking-map python3 -c "
import sqlite3
conn = sqlite3.connect('/app/db/hitchhiking-prod.sqlite')
conn.execute('ALTER TABLE <table_name> ADD COLUMN <col_name> <type>')
conn.commit(); conn.close()
"
```
Failure to do this causes `sqlalchemy.exc.OperationalError: no such column: <table>.<col>` on any query that touches that model, which presents as a 500 for every affected route.

### Container killed by OOM (exit code 137)
If the `hitchhiking-map` container is down with exit code 137 (`Exited (137)`), it was killed by the Linux OOM killer. This happened on 2026-04-07.

**Diagnosis steps:**
1. `sudo docker ps -a --filter name=hitchhiking-map` — check exit code (137 = SIGKILL)
2. `sudo docker logs --tail 100 hitchhiking-map` — look for `Killed` at the end with no Python traceback (confirms external kill, not app crash)
3. `sudo docker inspect hitchhiking-map --format '{{.State.OOMKilled}}'` — if `false`, the OOM came from the **host kernel**, not a Docker memory limit
4. `dmesg -T | grep -i -E "oom|kill|out of memory" | tail -20` — shows which process triggered the OOM killer

**Known cause:** `mysqld` on this host consumes ~2.2 GB+ RSS and pushes the system into OOM. The hitchhiking-map app itself uses SQLite, not MySQL — mysql is from another service on the same host. When the kernel OOM killer fires, it may kill the container's process as collateral.

**Recovery:** `sudo docker start hitchhiking-map`

**Prevention (not yet done):**
- Tune `mysqld` memory usage (e.g. lower `innodb_buffer_pool_size`)
- Add swap or more RAM to the host
- Set a Docker memory limit on the container so Docker's own OOM handling kicks in before the kernel's indiscriminate kill

## Temporary workarounds (revert when relay is fixed)

While the maps.hitchwiki.org nostr relay setup is being debugged, the following temporary changes are in place. Revert all of them once the relay reliably accepts and serves events again:

1. **`docker-compose.yml`** — joins the external `relay.maps.hitchwiki.org` Docker network so the app can reach the relay container directly via `ws://relay.maps.hitchwiki.org:8080` instead of `wss://relay.maps.hitchwiki.org` (works around hairpin NAT on the host). When the public URL works again, drop the `networks:` blocks and revert `RELAYS` in `.env` to the public wss URL.
2. **`hitch/blueprints/utils/post_hitchhiking_ride_to_nostr.py`** — every signed event is also appended to `dist/temporary.json` as a local fallback record, independent of relay acceptance / `fetch_nostr` cron. Remove `_append_event_to_temporary_json` and its call site, plus the `json` / `pathlib.Path` imports, once we trust the relay round-trip again.
3. **`hitch/blueprints/utils/post_hitchhiking_ride_to_nostr.py`** — the event's `pubkey` field was changed from `self.npub` (bech32) to `self.pubkey_hex` (64-char hex) because relays were silently rejecting bech32-pubkey events. This one is actually a bug fix and should stay; do **not** revert it with the rest.

## Data Flow and Storage

### Data Sources
The application aggregates hitchhiking data from multiple sources:

1. **Nostr Protocol Network** (Primary ride data source)
   - **Source**: Decentralized Nostr relays (relay.maps.hitchwiki.org)
   - **Data Type**: Hitchhiking ride events (Nostr event kind 36820)
   - **Fetching**: Every 30 minutes via `fetch_nostr.py`
   - **Process Flow**:
     - Node.js script (`hitch/scripts/fetch_hitchhiking_events/src/index.ts`) fetches events from relays - relays might contain new rides from other apps and also new rides from this app that were directly sent to the nostr relay on creation (because doing it natively in .ts is easier than in python)
     - Writes raw events to `dist/allPosts.json` and `dist/allPosts.csv` (those are just intermediate files, actually we want the latest state of rides from nostr to go straight into our local database - we do this in the next step by recreating the database, this is simpler than only trying to sync the changes)
     - Python script (`fetch_nostr.py`) reads `dist/allPosts.json`
     - Parses JSON content and extracts ride metadata (stops, signals, ratings, etc.)
     - the nostr events can contain information about rides that this project does not support yet, all information that is supported is stored in RideEvent, we aim incorporate all information from the nostr rides in the furture
     - Stores in `RideEvent` table with full deletion/recreation on each fetch
   - **Output Files** (in `dist/` directory):
     - `allPosts.json` - Raw Nostr events in JSON format
     - `allPosts.csv` - Raw Nostr events in CSV format

2. **OpenStreetMap** (Official hitchhiking spot locations)
   - **Source**: Overpass API query for `highway=hitchhiking` tags
   - **Data Type**: Official designated hitchhiking spots
   - **Fetching**: Manual/periodic via `sync_osm.py`
   - **Storage**: `OsmHitchhikingSpot` table (lat/lon, tags, metadata)
   - **Purpose**: Link user-submitted rides to official spots within 100m radius

3. **Hitchwiki** (Community wiki articles)
   - **Source**: Hitchwiki MediaWiki API (hitchwiki.org/en/)
   - **Data Type**: Article coordinates from `{{Coords|...}}` templates and embedded maps
   - **Fetching**: Manual/periodic via `sync_hitchwiki.py`
   - **Storage**:
     - `HitchwikiArticleLocation` - Article paragraph coordinates with section headings
     - `HitchwikiArticleMap` - Embedded map coordinates with zoom levels
   - **Purpose**: Link rides to relevant wiki articles (and specific section) and link spots to city articles if they are within the map that is shown for a city

4. **OpenStreetMap car-pooling spots**
   - **Source**: Overpass API (amenity/highway car-pooling tags)
   - **Fetching**: Daily via `sync_car_pooling.py`
   - **Storage**: `OsmCarPoolingSpot` table
   - **Purpose**: Surface nearby car-pooling spots on the map (the `cp` flag in `spots.json` and `car_pooling` field in per-spot files)

### Database Storage (SQLite)

**Primary Database**: `db/hitchhiking.sqlite` (configured via `DATABASE_URI` in `hitch/settings.py:57-58`)
- **Location**: `db/` directory (relative to project root)
- **Default name**: `hitchhiking.sqlite` (dev), `hitchhiking-prod.sqlite` (production via `DATABASE_NAME` env var)
- **Path resolution**: `{project_root}/db/{DATABASE_NAME}`

#### Database Initialization
The database must exist before the application can run. Two initialization paths:

1. **Fresh Start**: `flask init` (`hitch/__init__.py:84-101`)
   - Creates all tables via `db.create_all()`
   - Creates default roles (admin, monitor, user, reader)
   - Runs `flask generate-all` to populate initial data
   - Tables are created from models in `hitch/models.py`

# TODO: not sure if this is true/necessary
2. **Production Setup**: Download pre-populated database
   - `curl https://hitchmap.com/dump.sqlite > db/hitchhiking.sqlite`
   - Contains historical ride data from legacy hitchmap.com
   - Can be synced with upstream via `sync_upstream.py` (daily at 7 AM)

#### Core Sqlite Tables (see hitch/models.py for the database schema)
We use the sqlite tables as a canonical format to easily translate between the nostr data and the data we serve to the frontend via .json files and to store some that is not updated frequently information (e.g. about hitchwiki articles and osm).
**Tables Written by Application:**

- **`ride_event`**: All Nostr ride events
  - Full Nostr event structure (id, pubkey, sig, created_at, tags)
  - Parsed content fields: stops, signals, hitchhikers, rating, waiting_duration
  - Extracted coordinates: start lat/lon, destination lat/lon
  - User metadata: hitchhiker nicknames, submission times
  - **Written by**: `fetch_nostr.py:33-74` (full table delete/recreate every 30 min)
  - **Read by**: `show.py:57`, `main.py:64,191` (ride submission/editing)

- **`osm_hitchhiking_spot`**: OSM official spots (id, latitude, longitude, tags)
  - **Written by**: `sync_osm.py:36-50` (full table delete/recreate on sync)
  - **Read by**: `show.py:310` (to link rides to nearby OSM spots)

- **`hitchwiki_article_location`**: Wiki article coordinates (lat/lon, title, heading, URL)
  - **Written by**: `sync_hitchwiki.py:213-230` (full table delete/recreate on sync)
  - **Read by**: `show.py:338` (to link rides to wiki articles)

- **`hitchwiki_article_map`**: Wiki embedded maps (lat/lon, zoom, title, URL)
  - **Written by**: `sync_hitchwiki.py:237-258` (full table delete/recreate on sync)
  - **Read by**: `show.py:343` (to link rides to wiki map views)

- **`user`**: User accounts (Flask-Security managed)
  - **Written by**: Flask-Security registration flow
  - **Read by**: `main.py:28-41` (ride ownership verification)

- **`co_hitchhiker`**: Co-hitchhiker acceptance tracking (nostr_ride_event_d_tag, co_hitchhiker, accepted)
  - **Written by**: `main.py:216-222` (when ride submitted with co-hitchhikers)
  - **Purpose**: We want to know which users were on a ride together, if so there are two rows in this table with the same nostr_ride_event_d_tag and different references to co_hitchhiker, a co_hitchhiker can be added by the creator of the ride, but has to be accepted by the other user, then both users show up on the frontend for this ride and both can edit the ride
  - **Read by**: Not currently queried (future feature)

# TODO: is this needed or deprecated stuff? specifically when do we use sync_upstream
**Legacy Tables (from upstream sync):**
- **`points`**, **`duplicates`**, **`service_areas`**, **`road_islands`**
  - Synced from hitchmap.com dump via `sync_upstream.py:23-28,97-132`
  - Used for routing and legacy data compatibility
  - Read by: `show.py:57` (via pandas `read_sql`), `main.py:253` (duplicate reporting)

### Generated JSON Files

**Location**: `dist/` directory (relative to project root)
- **Path resolution**: `{project_root}/dist/` (`helpers.py:24-36`, `get_dirs`)
- **Served by**: Flask at `/<path>` routes (`__init__.py:199-225`, `catch_all`)

#### Files Generated by `fetch_nostr.py` (via Node.js script) - not needed to serve the app
- **`allPosts.json`** - Raw Nostr events in JSON format
- **`allPosts.csv`** - Raw Nostr events in CSV format

#### Files Generated by `show.py` - we find it simpler to serve data to the app via those files than from the database by just sending them to the frontend
The `show.py` script runs every 10 minutes and generates map data files from the database:

1. **`spots.json`** - Aggregated hitchhiking spots (downloaded by every visitor on map load, so it's kept slim: only what's needed to draw and filter markers)
   - Groups rides by exact lat/lon coordinates; output coordinates rounded to 5 decimals (~1 m)
   - Structure: `{lat, lon, rating, review_count}` (`review_count` = total ride entries at the spot; the spot id is not stored — the frontend derives it from lat/lon as `lat.toFixed(5)_lon.toFixed(5)`, matching `generate_spot_id`; 5 decimals (~1.1 m) is finer than the 5 m merge radius so distinct anchors never collide on one id) plus, only when present: `latest_ms` (epoch ms of newest submission), `dest_lats`/`dest_lons`, and presence flags `osm`/`cp`/`wiki`/`wikimap` (booleans, omitted when false)
   - Click-time detail (wait/distance averages, OSM / car-pooling / Hitchwiki links) lives in the per-spot files instead
   - Low-value rides — anonymous AND no comment AND no wait time (rating only) — are dropped from all detail views (`places` aggregations, per-spot files, `rides_index`, `recent`); a spot whose rides are all low-value is removed entirely. Such rides are still counted in `review_count` of any spot that keeps ≥1 informative ride (`total_ride_counts` is computed before the filter in `show.py`)

2. **`rides_index.json`** - Lightweight index of all rides (replaces deprecated `rides.json`)
   - One compact entry per ride, used by the map UI to power filters, search, and the recent-rides list without loading full popup details
   - Fields are short-keyed to keep the file small: `{id, sid (spot_id), lat, lon, u (hitchhiker_name), t (submission_time ms), r (rating), km (distance), osm (bool), wiki (bool), c (truncated comment excerpt)}`
   - Loaded once on map startup (`map.js` fetches `/rides_index.json`)

3. **`rides/by-spot/<spot_id>.json`** - Per-spot detail files
   - One JSON file per spot, written under `dist/rides/by-spot/`
   - Shape: `{"spot": {wait, distance, osm_id, car_pooling, hitchwiki_article, hitchwiki_map}, "rides": [{id, rating, wait, comment, hitchhiker_name, submission_time, ride_datetime}, ...]}` — `spot` holds the click-time info slimmed out of spots.json (keys omitted when absent)
   - Fetched lazily by the frontend only when a marker is clicked (`map.js` handleMarkerClick merges `spot` into the marker data and re-renders the summary)
   - The `by-spot` directory is wiped and rewritten on each `show.py` run so deleted spots don't leave stale files

4. **`spots_recent.json`** - Latest 1000 rides
   - Sorted by submission time (descending)
   - Used for tabular "Recent Rides" page
   - Includes ride URL, timestamp, username, rating, distance

5. **`heatmap.json`** - Predicted waiting times
   - Generated using sklearn Gaussian Process model
   - RGBA image overlay data (lat/lon bounds: -56 to 80, -180 to 180)
   - Legend with color boundaries for waiting time visualization
   - Can be disabled via `GENERATE_HEATMAP=False` config

**Note**: JSON regeneration is optimized - files are only rebuilt when database modification time is newer than existing JSON files (unless `--force` flag is used).

### Data Flow Summary

```
Nostr Relays → fetch_hitchhiking_events/index.ts → dist/allPosts.json
                                                   ↓
                                        fetch_nostr.py → RideEvent table
                                                         ↓
OSM Overpass API → sync_osm.py → OsmHitchhikingSpot table ↓
                                                            ↓
Hitchwiki API → sync_hitchwiki.py → HitchwikiArticle* tables ↓
                                                              ↓
                                                         show.py
                                                              ↓
                                  dist/{spots,rides_index,spots_recent,heatmap}.json
                                          + dist/rides/by-spot/<sid>.json
                                                              ↓
                                                        Map UI (map.js)
```

### Ride Creation/Update Flow

When a user submits a new ride or edits an existing one:

1. **Immediate**: Flask validates form data → publishes ride event directly to Nostr relays (synchronous, ~5 sec) → returns redirect to `/#success`
   - No immediate write to the local `RideEvent` table — the ride only exists on Nostr relays at this point
   - Exception: co-hitchhiker records ARE written to the local `CoHitchhiker` table immediately, because co-hitchhiker acceptance is app-local state (not stored on Nostr). The submitter lists co-hitchhiker usernames, and each co-hitchhiker must accept via `/accept-co-hitchhiking-ride/<d_tag>` — this acceptance workflow only exists in the local DB.
   - For edits, the updated event is re-published to Nostr with the same `d_tag`
2. **up to ~30 min later**: `fetch_nostr` cron runs (every 30 min) → Node.js fetches all events from relays → Python deletes & rebuilds entire `RideEvent` table (ride now in local DB)
3. **up to ~10 min later**: `show.py` cron (every 10 min) detects DB modification → regenerates `spots.json`, `rides_index.json`, etc.
4. **Ride appears on map** — total latency up to ~40 minutes after submission

```
User submits form
    ↓ (immediate)
Flask → Nostr Relays (publish ride event)
    ↓ (redirect to /#success, ride NOT on map yet)
    ...
    ↓ (up to ~30 min, cron)
fetch_nostr → Nostr Relays → dist/allPosts.json → RideEvent table
    ↓ (up to ~10 min, cron)
show.py → dist/{spots,rides_index,spots_recent,heatmap}.json
        → dist/rides/by-spot/<sid>.json (one file per spot, lazy-loaded)
    ↓
Map UI loads updated JSON → ride visible on map
```

### Cron Schedule (deploy/cron.sh)
- **Every 30 minutes**: `fetch_nostr` - Fetch new rides from Nostr
- **Every 10 minutes**: `show` - Regenerate JSON map data
- **Daily at 2 AM**: `build_ride_routes.py --skip-detailed` - Rebuild the routing graph (`dist/repeatable_routes.json`, `dist/oneoff_routes.json`, `dist/test_routes.json`). Not a `flask generate` script — cron calls the file directly with `python3`
- **Daily at 3 AM**: `sync_osm` - Sync OSM hitchhiking spots
- **Daily at 3:30 AM**: `sync_car_pooling` - Sync OSM car-pooling spots
- **Daily at 3:45 AM**: `sync_fuel` - Sync OSM fuel / gas stations near spots
- **Daily at 4 AM**: `sync_hitchwiki` - Sync Hitchwiki article coordinates
- **Daily at 4:15 AM**: `sync_events` - Sync Hitchwiki `Category:Events` into `dist/events.json`
- **Daily at 5 AM**: `dashboard` - Regenerate analytics dashboard
- **Daily at 6 AM**: `cities` - Regenerate per-city pages
- **Daily at 7 AM**: `sync_upstream` - Upstream (legacy hitchmap.com) data synchronization
- **Daily at midnight**: `notify_nearby_hitchhikers` - Send nearby-hitchhiker notification emails
- **Weekly (Sun 1 AM)**: `backup_to_drive.py` - Scrubbed SQLite backup to Google Drive. Runs before the 2 AM routing rebuild so the two heaviest jobs on this OOM-prone host don't overlap (the backup holds a full ~400 MB snapshot plus its gzip on disk)
- **Weekly (Mon 8 AM)**: `sync_hitchhiking_rides_dataset` - Push rides to the Hugging Face dataset
- **Monthly (1st, 9 AM)**: `country_ratings` - Regenerate country hitchability CSV + `country_ratings.json` / `country_insights.json`

(Several legacy jobs — `dump`, `fetch-roads`, `fetch-areas` — are commented out in `deploy/cron.sh`.)
