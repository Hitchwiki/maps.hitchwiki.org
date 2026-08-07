# CLAUDE.md

> ## ⚠️ Other agents are working in this repo at the same time
>
> **Never discard work you did not write.** Multiple Claude Code sessions edit this
> checkout concurrently, and the working tree can gain changes at any moment — including
> while you are mid-task.
>
> - **Never** run `git checkout -- <file>`, `git restore`, `git reset --hard`, `git clean`,
>   or `git stash` on files you didn't change. There is no branch to recover them from
>   (this repo commits straight to `main`), so a discarded edit is gone for good.
> - **Stage explicitly.** `git add <specific files>`, never `git add -A` / `git add .` —
>   otherwise you sweep another agent's half-finished work into your commit.
> - **Re-check `git status` right before committing.** Files you never touched appearing
>   there is normal; leave them alone.
> - **Never `git push --force`.** Pull/rebase and push normally; if a push is rejected,
>   `git pull --rebase` and retry.
> - Before editing a file, prefer re-reading it — another agent may have changed it since
>   you last looked.

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
  - Preview assets are built by `hitch/scripts/route_preview.py` into `dist/dir/<key>.{json,png}` (OG title/description + a 600x315 OSM basemap with the route drawn on it), and served by `render_directions_preview`. Generation runs in a **subprocess**, single-flighted by a `<key>.json.lock` file: the routing graph costs ~190 MB and ~3 s to build, which must not live in the waitress workers. Stale locks (killed builder) are reclaimed after `2 * PREVIEW_TIMEOUT_S`. Cold hit ≈ 4-7 s; afterwards it's a file read. OSM tiles are cached forever under `dist/tiles/<z>/<x>/<y>.png`, so each tile is fetched at most once.
  - The route facts come from `hitch/scripts/repeatable_router.py` (the Python twin of `static/routing.js` — keep them numerically identical), and the endpoint labels from Photon reverse geocoding, preferring its `city` field over `name` (which is otherwise the nearest street or POI). `reverse_geocoder` is the offline fallback.
- **The viewport hash is rewritten on `moveend` via `replaceState`**, never `pushState` — a pan is not a navigation. `updateMapHash()` refuses to touch the hash when it holds navigation state (`#menu`, `#routing`, `#country/<name>`, `#insights`, `#dir/…`).
- **Legacy `?lat=&lon=` and `#lat,lon` links still resolve** and are rewritten in place to the canonical path (`setSpotUrl` → `replaceState`, since canonicalising is not a navigation and `pushState` would make the back button bounce onto a URL that reopens the same spot).
- Coordinate precision in the hash follows OSM's `zoomPrecision` (`ceil(log(zoom)/LN2)`), so shared links stay short at low zoom. This only affects the map centre, never spot identity.
- `sw.js` normalises `/spot/<id>` and `/dir/<from>/<to>` to `/` in its cache key: both render the same template (only the OG tags differ, and crawlers don't run the service worker), so they share one cached copy and work offline.

### Ride dates carry their weekday
Every ride date the site displays is prefixed with a localized weekday abbreviation — "Sa. 2026-08-01 11:32", "土 2026-08-01 11:32". Which day of the week a ride happened is a hitchhiking fact of its own (a Sunday service area is a different place than a Tuesday one) and nobody counts it back from a bare date. The filter pane has a matching **Day of week** picker (`?weekday=sat`, plus grouped `weekdays` / `weekend`).

- **`hitch/translations/weekdays.py`** is the single source: CLDR abbreviated + stand-alone-wide names for all 31 `SUPPORTED_LANGUAGES`, indexed Monday-first (`date.weekday()`). Baked in as a literal because Babel isn't in `requirements.txt` and the stdlib `locale` module needs OS locales the slim container doesn't have. Regenerate with Babel the way the module docstring describes if the language list grows — `tests/test_weekdays.py` fails when a language is missing.
- **The server side is a Jinja global**, `with_weekday(stamp)`, applied at render time — *not* baked into the ride-card dicts. `show.py` writes its cards once from cron for pages that are then rendered in all 31 languages, so a stored weekday would be wrong for 30 of them. Applied in `_ride_card.html` (which covers the activities feed, leaderboards, profiles, trips, `/recent`), `my_rides.html`, `ride_detail.html` and `route_template.html`. `route_pages.py` renders through its own bare `Environment` and has to register the global itself, like `t`/`g`.
- **Only the leading `YYYY-MM-DD` is read**, never the offset: the stamp is already the ride's own local wall-clock time, and re-interpreting it would move a ride logged near midnight onto the wrong day.
- **The client side gets the same table injected** as `window.__WEEKDAYS__` (`client_weekdays_json()`, set in `map.html`), used by `map.js` `formatRideDate`/`formatRideDateTime` and `account.js`. Deliberately not `toLocaleDateString(…, {weekday})`: a server-rendered card and a client-rendered one sit on the same page, and browser ICU data for Georgian/Mongolian isn't something we can assume.
- **The weekday filter keys on `rd ?? t`** in `rides_index.json` — the ride's own datetime, falling back to its submission time, which is exactly the rule the card's printed date follows, so the filter always agrees with what you see. Keying on `rd` alone would be purer but hides ~87% of rides (only ~10k of 74k records carry a ride datetime).
- The picker's option labels come from the weekday table, and the grouped options are written as ranges of abbreviations ("Mo.–Fr.", "сб–вс") so they need no translated string. Only the field label `t("Day of week")` is translated — **not** "Weekday", which every model renders as *workday* (Будний день / 工作日 / giorno feriale), the opposite of the weekend.

### `/why-not-hitchhike` — weekday patterns you could plan around
Spots where the same weekday produced the same faraway destination more than once, fast every time. A spot is listed when, for one weekday, **≥4 rides** from it ended within **25 km** of each other, that cluster sits **≥100 km** from the spot, and **every** ride in it waited **under 30 min**. Route in `main.py` (`why_not_hitchhike`), template `why_not_hitchhike.html`, data precomputed by `hitch/scripts/why_not_hitchhike.py` into `dist/why_not_hitchhike.json` (weekly cron, Mon 07:00).

- **One slow ride kills a cluster.** The page's claim is "you can count on this", not "it usually works", so a single counter-example has to be able to break it. That is also why the thresholds are published in the JSON and rendered on the page — changing a constant changes what the page asserts.
- **Weekday comes only from `departure_time`, never the `rd ?? t` fallback** the filter above uses. That fallback is right for a filter (it agrees with the printed card date) and wrong here: this page asserts something about the day people *rode*, and a submission stamp is the day someone typed it in, often weeks later. The cost is ~87% of the corpus — ~9.1k rides carry a departure time, a destination *and* a wait together.
- **Duplicate submissions are collapsed** (same spot + hitchhiker + departure instant + destination + wait). Before that rule the only cluster in the whole dataset meeting every criterion was one hitchhiker's ride submitted four times within 19 seconds — a page-worth of evidence that was really one ride.
- **Reads `dist/rides_index.json` for spot identity rather than re-clustering.** Row `spot_id`s are then the same ids `/spot/<id>` and the per-spot files use; re-deriving the 5 m merge + service-area grouping here would silently disagree. Makes the script a strict downstream of `show`.
- **Near misses are a separate section**, each row naming the criterion it missed, and every one must span ≥2 distinct dates — three rides on one afternoon say nothing about a weekday. As of 2026-08-05 the strict list is **empty** and there are 9 near misses; the empty state prints the coverage numbers, because "no spot exists" would be false where "we can't show one yet" is true.
- Weekday **names** are resolved in the route from `weekday_names()`, not stored in the JSON — same 31-language reason as the ride cards above.

### Filters reach the spot pane, not just the markers
A filter that describes a *ride* also decides which rides the open spot pane lists. A spot survives a "Saturdays only" filter because *some* ride there matched; listing its Tuesday rides next to that one answers a question nobody asked.

- **One predicate, `map.js` `buildRideFilter()`**, is the single owner of "does this ride match": user, vehicle, signal method, ride-date range, weekday, comment search, min distance, Last 24h. Returns `null` when nothing is active, so callers skip the pass. Three callers — `applyParams` (which spots stay on the map), `applyRideFilters` (`#insights`), `applySpotRideFilter` (the pane). They used to be three near-copies that had already drifted.
- **`buildRideFilter({attributesOnly: true})`** is what `applyParams` uses. It drops min-distance and Last-24h, which that path answers at *marker* level instead (against the spot's whole destination list, and its newest ride) — keep it that way or spot selection changes.
- **It takes both ride shapes.** `rides_index.json` is short-keyed (`u`/`v`/`m`/`km`/`c`/`rd`/`t`), the per-spot files and `/pending_rides.json` are not (`hitchhiker_name`/`vehicle_kind`/…). The `rideUser`/`rideVehicle`/… accessors are the only place that knows both names; they test `undefined`, not null, because the index always carries its keys while the per-spot files omit sparse ones. Accessors rather than one normalised object on purpose: the predicate runs over all ~74k index entries on every keystroke in the search box.
- **Spot-level filters never hide a ride in the pane** (min rides per spot, min rating, official spot, car pooling, gas station) — they aren't facts about a ride, and the marker already passed them.
- **The summary is recomputed from the filtered subset** (`spotAverages`), because a filtered histogram under an unfiltered average is two different claims about one spot. The marker's own `_data` keeps the unfiltered values; the filtered ones go into a throwaway copy. `_data.allRides` holds everything fetched, so clearing a filter puts rides *back*.
- `applyParams` ends by calling `refreshOpenSpotRides()` — filters can be changed with a pane open (on `#insights` the pane is mounted right above the charts), and both branches must re-derive it.
- Known asymmetry: the map's comment search runs on the index's 200-char excerpt, the pane's on the whole comment, so a needle past that cut matches in the pane but not on the map. That's the right way round for a search box.

### The Activities button carries a dot when /recent has something new
The map's bottom-pane **Activities** button (`map.html` `#action-activities`) shows a red dot for logged-in visitors, decided server-side by `main.activities_badge()` and rendered like the account button's notification bell. Two reasons, both meaning "there is something on this page worth opening": the viewer **follows nobody** (the page answers exactly that case with its follow suggestions), or someone they follow **contributed since they last looked**.

- **"Last looked" is `user.recent_seen_at`**, epoch seconds, stamped by `/recent` itself (`recent_spots`) from a timestamp taken *before* the feed is read — a ride published while the page renders isn't on it and must still count as unseen. NULL = never opened. Column added by `hitch/scripts/migrate_recent_seen_at.py`.
- **Compared against `RideEvent.created_at`**, the Nostr event's own epoch-seconds stamp and an indexed column — never `submission_time`, which is a string in the submitter's local wall-clock time and so cannot be ordered against a server timestamp at all. An edit republishes under a fresh `created_at`, so an edited old ride counts as activity.
- **`BADGE_LOOKBACK_S` (30 days) is a performance bound, not a product rule.** The query runs on the app's most-requested route; against prod it costs 53 ms for a viewer who last looked a month ago, 10 ms for a week, 2 ms for a day — and 556 ms with no bound at all. Anonymous visitors and the ~97% of accounts that follow nobody never reach it (they short-circuit on the follow list).
- Cleared on click as well as by the visit (`map.js`), because the button opens `/recent` in a new tab and this page stays put.

### A hitchhiker's name is a case-insensitive identity
Rides carry a free-text `nickname`, not a foreign key to `user`, so "is this ride mine", "whose profile is this" and "who do I notify" are all string comparisons. **`hitch/usernames.py` owns that comparison** — `username_key` / `same_username` / `find_user_ci` / `canonical_username`. Never compare two hitchhiker names with `==`.

- **The whole name is compared case-insensitively**, not MediaWiki's first-letter rule (the old `_norm_nickname`). A Hitchwiki account arrives through OAuth spelled the way the wiki stores it ("Germanytoindia") while the same person's imported hitchmap.com rides carry what they typed there ("GermanyToIndia"); under the first-letter rule those were two people, and the rides sat on a stub page their own author could not edit, be credited for, or be followed on. 18 of 216 accounts had rides under a differently-cased spelling.
- **Display and links use the registered account's spelling** (`canonical_username`): applied in `show.py` right after `get_hitchhiker_name` — before anything groups on the name, so the per-user lifetime stats stop splitting one person in two — and identically in `ride_facts.hitchhiker_name` (the live `/pending_rides.json` path) and `user.py` `_extract_ride_info` (every server-rendered ride card). An unregistered nickname passes through exactly as logged.
- **`/account/<other spelling>` 301s onto the account's own URL**, keeping the `/<lang>` prefix (`url_for(request.endpoint, …)`) — one person must not have two profile pages, each holding half their rides.
- **"Anonymous" is a sentinel, not a person** — never canonicalised, in either implementation, or an account registered under that name would capture every unattributed ride.
- **In SQL the rule is `lower(...)`**, which SQLite applies to ASCII only, so a name differing in a non-ASCII letter past the first ("Hélia"/"HÉLIA") stays two names. Known and accepted; fixing it needs a custom collation.
- `CoHitchhiker` rows are written under the invited account's own spelling (that is what their accept/reject looks up), but read case-insensitively, since older rows carry whatever the inviter typed.
- Tests: `tests/test_username_case.py`.

### Key Models
`hitch/models.py` defines ~15 models; the most relevant:
- **RideEvent**: Stores Nostr ride events with JSON content and extracted columns
- **OsmHitchhikingSpot** / **OsmCarPoolingSpot**: OpenStreetMap hitchhiking / car-pooling spot locations
- **HitchwikiArticleLocation** / **HitchwikiArticleMap**: Hitchwiki article coordinates and embedded map views
- **CoHitchhiker**: Co-hitchhiker acceptance tracking
- **User** / **Role**: Flask-Security accounts and roles
- **Follow** / **Notification**: User following and notifications
- **Trip** / **TripRide**: Trips grouping multiple rides. `Trip.user_id` is **nullable**: a multi-ride journey logged anonymously through the in-ride tracker is auto-grouped into an ownerless trip (see the in-ride tracker section). An ownerless trip is reachable only by its link — every trip-mutating route compares `trip.user_id` to a logged-in id, which `None` never equals — and any `db.session.get(User, trip.user_id)` must be guarded, since `session.get` with a `None` pk raises rather than returning `None`
- **RideReport**: User-reported issues on rides
- **RideImage**: A photo attached to a ride, keyed by the ride's Nostr `d` tag. Local-only — never published to Nostr (see the ride-photos section below)
- **SpotName**: Cached reverse-geocoded street name per spot id (see `spot_names.py`)
- **ServiceArea** / **RoadIsland** / **RoutingSearch**: Routing-support data

### Data Processing Scripts (hitch/scripts/)
- **fetch_nostr.py**: FULL Nostr fetch — Node.js `dist/index.js` re-fetches the entire kind-36820 history and Python delete-and-recreates the whole `ride_event` table. Also the only writer of the public `dist/allPosts.json` / `allPosts.csv` exports. Now runs **weekly** (Mon 00:51), not every 30 min: re-fetching + re-serialising 75k events / 100+ MB pinned a CPU core for a minute+ every half hour. Only still needed to catch **back-dated events** (a `since` query skips them) and to refresh the public exports before the Monday HF dataset push — deletions are now handled incrementally.
- **fetch_nostr_incremental.py**: INCREMENTAL Nostr fetch (runs every 5min via cron). Asks the relay only for events with `created_at >=` the newest ride we already hold (Node.js `dist/index_incremental.js`, `SINCE` env → `dist/newPosts.json`), then **upserts** them keyed on the addressable coordinate `(pubkey, d)`, newest-`created_at`-wins. Because a kind-36820 edit reuses the same `d` under the same `pubkey` but re-publishes with a fresh `created_at` (~now) and a new event `id`, a `since` query always catches edits — even to old rides; the upsert overwrites the row in place (including its PK `id`). **Deletions:** the same run fetches ALL kind-5 (NIP-09) deletion events (they're rare/tiny, so no watermark → never miss one → `dist/newDeletions.json`) and removes each referenced ride, but only when the deletion's `pubkey` matches the stored ride's `pubkey` (author-only, so a forged delete can't wipe someone else's ride). The one thing left for the weekly full run is back-dated events. Steady state is sub-second. Both scripts share `parse_post_to_ride_fields` (`hitch/scripts/nostr_ride_parsing.py`) so their extracted columns never drift, and share `/tmp/fetch_nostr.lockfile` so they never overlap.
- **show.py**: Generates map data views (runs every 10min via cron). The four "is there an X within 100 m of this spot" lookups (OSM hitchhiking spot, car-pooling, fuel, Hitchwiki article) all go through one shared 0.01°-cell spatial grid, `build_point_grid` / `find_nearest_in_grid`. Three of them used to full-scan their whole feature table per spot — 37k spots × (1.2k + 2.7k + 5.1k features) ≈ 337M haversine ops, ~160 s of a ~330 s run, measured identical output and ~37× faster once gridded. The grid is safe for a 100 m radius even at the northernmost spot we hold (78°N): the radius is *road-factored* by `haversine_np`'s 1.25, so it's 80 m as the crow flies, while 0.01° of longitude is still ~225 m there. Ties are broken by table order so the grid returns exactly what the previous `argmin` did
- **dashboard.py**: Analytics dashboard generation (daily)
- **cities.py**: Per-city page generation (daily). Renders `dist/city/<Country>/<City>.html` **plus** `/<lang>/city/...` for the top `TOP_N_TRANSLATED` (400) cities in every supported language, and is the sole writer of `sitemap.xml` / `robots.txt` (so a crash here silently freezes both — that happened when i18n landed). It renders through its **own bare Jinja `Environment`**, which must be given `t`, `g` and `SUPPORTED_LANGUAGES` as globals: `base.html` uses `{{ g.lang }}` and `t()`, and an UndefinedError there aborts every page. Setting `g.lang` per language is what drives translation, since `translations.current_lang()` reads it. Also exports `dist/city/top_cities.json` (the ride-volume ranking) for `route_pages.py`. Not all cities get every language: 14.5k × 31 is ~450k pages / ~7 GB, and translating only the furniture around untranslated reviews is thin duplicate content at that scale.
- **route_pages.py**: "Hitchhiking from X to Y" pages for well-evidenced city pairs (daily at 5:30 AM, **before `cities`**). These exist because `/dir/<from>/<to>` is permanently `noindex` (quadratic URL space), leaving nothing crawlable to answer "how do I hitchhike from Berlin to Munich". Reads `top_cities.json`, builds the routing graph **once** (~190 MB, ~1.8 s) and reuses it for every pair at ~290 ms each — never in a web worker, this host has been OOM-killed. Publishes only pairs where every leg has ≥2 logged rides and the route passes spots with ≥3 rider comments, capped at `MAX_PAGES`; the cap and the evidence bar are deliberate, since mass-produced near-identical pages are the doorway-page pattern that gets a whole domain penalised. Writes `dist/route/index.json`, which `cities.py` folds into the sitemap.
- **why_not_hitchhike.py**: Weekday patterns behind `/why-not-hitchhike` (weekly, Mon 7 AM) — see the section of the same name above for the criteria and the two data rules (departure-time-only weekdays, duplicate collapsing) that decide whether the output means anything. Reads `dist/rides_index.json`, so **it must run after `show`**; also wants `ride_places` (4:45) and `spot_names` (4:30) to have named the endpoints it prints. Cheap (~10 s): the clustering only ever runs within one spot's rides for one weekday.
- **dump.py**: Database export functionality
- **sync_osm.py**: OSM hitchhiking-spot synchronization (fetches highway=hitchhiking spots, daily)
- **sync_car_pooling.py**: OSM car-pooling spot synchronization (daily)
- **sync_fuel.py**: OSM fuel / gas station synchronization (`amenity=fuel`, daily at 3:45 AM). A *global* fuel query is far too large for the public Overpass servers (hundreds of thousands of elements → reliable 504), and fuel is only used to flag hitchhiking spots that sit *at* a gas station (`show.py`, 100 m match, the `fuel` flag in `spots.json` / `fuel` field in per-spot files). So the script reads spot coordinates from the already-generated `dist/spots.json`, reduces them to 1° tiles, and queries Overpass for fuel only inside those tiles — batched ~60 bboxes per union request with 429/504 retry-and-backoff. **Depends on `spots.json` existing, so it must run after `show`.** `show.py` resolves this (and every other "is there an X within 100 m" question) through one shared spatial grid — see `build_point_grid` / `find_nearest_in_grid` there.
- **sync_hitchwiki.py**: Hitchwiki article synchronization (extracts coordinates from wiki articles, daily)
- **sync_events.py**: Hitchwiki events synchronization. Pulls every page in `Category:Events`, extracts each `{{Event|name|start|end|lat|lon}}` template, keeps events whose end date is today or later, and writes `dist/events.json` directly (self-contained → no DB model, like `country_ratings`). The map draws a calendar-pin marker per event; clicking it opens a bottom sheet with the name, dates, a plain-text blurb from the wiki page, and a Hitchwiki link (daily at 4:15 AM). Note: Hitchwiki is behind Cloudflare, which 403s ("Just a moment…") requests without a browser-like `User-Agent`, so the script sends one.
- **build_ride_routes.py**: Builds the routing graph from rides (daily at 2 AM). For every ride with a destination it fetches an OSRM driving route and records which *other* known start spots lie within 300 m of the polyline, in travel order; sequences shared by ≥2 rides become the "repeatable" trees in `dist/repeatable_routes.json` (read by `static/routing.js`). The same run also writes `dist/oneoff_routes.json` — the identical trees with the ≥2 threshold dropped to 1 (so a corridor a single ride established still forms edges), indexing the *same* `spots` array and carrying a `spot_count` guard. The routers fetch/build it lazily and search it **only when the repeatable graph connects nothing** (`routing.js` `loadFallbackRouter` / `repeatable_router.py` `load_oneoff_router`); it's a ~6× larger superset (~3.4 MB), so it must not load on every map view. Routes that use a support-1 leg are flagged in the UI ("1 logged ride"). Standalone script (plain `python3`, not `flask generate`), reads SQLite directly. OSRM responses are cached in `dist/route_cache.jsonl` (~675 MB, read via a byte-offset index so geometries never all sit in RAM), so a daily run only fetches routes for rides added since the last run. Spot consolidation must stay identical to `show.py`'s (5 m merge → service-area/road-island polygon grouping → snap onto `dist/spots.json`), otherwise routes reference phantom spots with no map marker.
- **backup_to_drive.py**: Weekly off-site backup of the SQLite DB to Google Drive with PII scrubbed (Sundays at 1 AM). Standalone script (plain `python3`, stdlib only, no app context), not a `flask generate` one. Pipeline: online-backup-API snapshot (a plain `cp` of a live DB can capture a torn page) → scrub → `VACUUM` → gzip (~417 MB → ~99 MB, ~40 s) → `rclone copyto` → prune backups older than `BACKUP_RETENTION_DAYS` (28). **The `VACUUM` is part of the scrub, not an optimisation** — an `UPDATE` leaves the old email behind in freelist pages, recoverable from a file that looks clean via SQL. The scrub replaces `user.email` with `user<id>@example.invalid` (keyed by id because the column is UNIQUE; `.invalid` is RFC 2606 reserved so a restored backup can't mail a real person) and nulls `tf_totp_secret`, `us_totp_secrets`, `mf_recovery_codes`, `us_phone_number`, `tf_phone_number`, `last_login_ip`, `current_login_ip`. **`password` hashes are deliberately kept** so the backup can restore working logins; 2FA users would re-enrol. Note the scrub only covers the `user` table — ride comments sometimes contain emails hitchhikers typed in themselves, but that text is already public on the map. Config: `BACKUP_RCLONE_REMOTE=gdrive:hitchwiki_maps-backups` in `.env` plus `deploy/rclone.conf` (gitignored, generate per `deploy/rclone.conf.example`). Test with `--no-upload` (optionally `--keep-local <path>`); a full run takes ~5.5 min, mostly upload. Uses its own Google OAuth client (Cloud project `hitchwiki-maps`) — a blank `client_id` shares rclone's global client and 403s with `Quota exceeded ... project_number:202264815644`. **`deploy/rclone.conf.example` is the full setup runbook — read it before touching any of this.** The traps it covers, all hit for real during setup:
  - The OAuth consent screen must be **published ("In production")**, not left in **Testing**. Testing-mode refresh tokens expire after **7 days** and this job runs every 7 days, so it would yield one good backup then fail silently forever. Adding yourself as a Test user does *not* fix the expiry. (Publishing *unverified* is fine and unrelated — it only adds an interstitial.)
  - The conf is mounted **read-write** because rclone rewrites it with a refreshed access token roughly hourly (verified by backdating the expiry). `:ro` works for an hour, then breaks.
  - **The conf file must exist before the container starts.** Docker bind-mounts a missing source path by creating it as an empty *directory*, so `docker compose up` without it leaves a root-owned dir at `deploy/rclone.conf` and rclone silently has no remotes.
  - The Console's client secret JSON downloads to the **project root**, which is this git repo. `client_secret_*.json` is gitignored now, but check `git status` after any Console download.
  - Authorizing on this headless host: VS Code Remote-SSH already forwards `localhost:53682`, so `rclone authorize` run *on the server* completes in the laptop browser with no manual tunnel and no secret leaving the host.
- **spot_names.py**: Reverse-geocode spots into street names (daily at 4:30 AM). Standalone script (plain `python3`, not `flask generate`) filling the `spot_name` table — the last step of the naming cascade in `hitch/scripts/spot_naming.py`, which `show.py` uses to give each spot a display name instead of bare coordinates. The cascade is: OSM `highway=hitchhiking` spot ≤100 m → the `service_area` polygon the spot was merged into → fuel station ≤100 m → car-pooling spot ≤100 m → this cached geocode. The first four are free (those tables already store OSM `tags`, and `show.py` already picks the service-area polygon when merging), but only ~5.5k of 35k spots have any OSM feature nearby, so the geocode carries the rest. Photon at 1 req/s, `--limit N` per run (default 2000) so a cron run stays bounded; the initial ~30k backlog is a manual `--limit 0` run (~8 h). **Reads `dist/spots.json`, so it must run after `show`** (same dependency as `sync_fuel`). A row with a NULL `name` means Photon answered and the place has no street — never retried; a *failed request* writes no row at all, so an outage can't permanently mark thousands of spots unnameable.
- **sync_hitchhiking_rides_dataset.py**: Push rides to the Hugging Face dataset (weekly)
- **notify_nearby_hitchhikers.py**: Email notifications for nearby hitchhikers (daily)
- **Destination enrichment (occasional manual batch jobs, NOT cron; both write inferred destinations to the `derived_ride_location` table, keyed by Nostr `d`, distinguished by the `kind` column; `show.py` + `build_ride_routes.py` merge these onto rides that reached Nostr with no destination).** Standalone scripts (plain `python3`), run against the root-owned prod DB via `sudo`:
  - **extract_destinations.py** (`kind=derived-comment-city`): mines the ride's free-text comment for the city it actually reached, geocodes it (`is_exact=0`, city centre). Three stages: `prefilter` (needs app context) → `extract` (LLM, needs `OPENAI_API_KEY`) → `geocode-store --db <path>`.
  - **derive_consecutive_destinations.py** (`kind=derived-consecutive-ride`): reconstructs trips a named user logged in one sitting — a run of their no-destination rides logged minutes apart with starts marching in one bearing forms a chain, so each ride's destination = the next ride's logged start (`is_exact=1`, a real spot). Run `--db <path> --dry-run` to preview chains, then without `--dry-run` to write; `ON CONFLICT DO NOTHING` never clobbers a comment-derived row. **After running either, regenerate map data + routing graph in the container** (`show --force`, then `build_ride_routes.py --skip-detailed`) so the new destinations reach the map and routes.
- **build_admin1_borders.py**: One-off asset builder (plain `python3`, stdlib only, NOT cron) for `hitch/static/admin1_borders.geojson` — the state/province/federal-subject lines the map draws over the heatmap, from Natural Earth 1:50m admin-1. It keeps only edges **two** units share, so the output is internal borders alone: the national outline comes from `countries.geojson` (1:110m), and drawing it a second time from a different Natural Earth scale would show as two lines a few pixels apart. Edges are chained into long polylines *before* Douglas-Peucker, since simplifying each polygon separately moves shared vertices apart and tears neighbouring borders open. Re-run only to refresh the source data: `python3 hitch/scripts/build_admin1_borders.py` (downloads its own input; `--source <file>` for a local copy).
- Additional helpers: `fetch_osm_areas.py`, `fetch_osm_roads.py`, `sync_service_areas.py`, `sync_road_islands.py`, `routing.py`, `migrate.py`, `add-descriptions.py`

### Configuration
- **Environment-based**: BaseConfig + Development/Production/Testing configs in `hitch/settings.py`; selected via the `ENVIRONMENT` env var
- **Database**: SQLite with configurable paths via DATABASE_URI
- **Security**: Flask-Security with username-based auth, password hashing
- **Email**: Two paths — Flask-Mailman SMTP (defaults to SMTP2GO, `hitch/settings.py`) for Flask-Security mail, and SparkPost (`SPARKPOST_API_KEY` in `.env`) for welcome and nearby-hitchhiker emails (`hitch/blueprints/utils/send_welcome_email.py`, `send_nearby_hitchhikers_email.py`)

### Deployment
- **Pushing to `main` IS the deploy — there is no separate deploy step.** `.github/workflows/deploy.yml`
  fires on every push to `main`, SSHes into the prod host and runs `deploy/deploy.sh`, which does
  `git reset --hard origin/main` → `docker compose up -d --build` → prunes unused images/build cache
  → writes `logs/last_deploy.txt`. So don't hand-run `deploy.sh`, `docker compose build`, or
  `docker restart` after a push; just push and watch `logs/last_deploy.txt` flip to your commit
  (~1-2 min, a few seconds of 502 while the container swaps).
  - Because the script **`git reset --hard origin/main`s this checkout**, any uncommitted work another
    session has in progress here is destroyed by a deploy. Commit your paths before pushing, and note
    this is the mechanism behind "someone reset my working tree" surprises.
  - It also means a rebuild is *automatic*, so the "changes under `hitch/scripts/` need a rebuild"
    caveat elsewhere in this file resolves itself on push. Only reach for a manual
    `docker restart hitchhiking-map` when you have edited a **mounted** file (a template) and
    deliberately do *not* want to push.
- **Docker**: Dockerfile and docker-compose.yml for containerization
- **Cron**: Automated data fetching via `deploy/cron.sh` with file locking
- **Static Files**: Served from dist/ directory, includes PWA manifest
- **Web Server**: Waitress for production, Apache/NGINX reverse proxy configs provided

## Debugging & Operations

### Do not install or run a headless browser on the prod server
Never install or use Playwright, Puppeteer, Chromium, or any other headless browser on the
**prod server** — not even via `npx`. A browser download plus a live Chromium process is far
more disk and RAM than this host has to spare. On a local dev machine this is fine —
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

### Two containers: `hitchhiking-map` (web) and `hitchhiking-map-cron` (batch)
Same image, same mounts, different command — split on 2026-08-07. They used to be one container running `service cron start` alongside waitress, which put `show.py`'s ~1.6 GB peak (and `sync_fuel`'s ~1.9 GB) in the same cgroup as the web server; when the host ran out of memory the kernel OOM-killed `waitress-serve` at 826 MB RSS and the site 502'd. Nothing in `deploy/cron.sh` talks to the web app, so they had no reason to share.

- **`hitchhiking-map`** — `deploy/run.sh`: `flask init`, then waitress. `mem_limit: 2g`. Not tighter because `/dir/` link previews spawn `route_preview.py` subprocesses (~190 MB each) that are children of this container and single-flighted per route key, so several can build at once.
- **`hitchhiking-map-cron`** — `deploy/run_cron.sh`: `exec cron -f`, nothing else. `mem_limit: 3g`, above the heaviest job's observed peak. `depends_on` the web container purely so `flask init` (create_all + roles + generate-all) isn't raced on a fresh DB.
- The crontab is installed into the **image** (`crontab /app/deploy/cron.sh` in the Dockerfile), so both containers carry it and only the cron one starts `cron`.
- **After a deploy, check both are up** — if the cron container fails to come up, the site keeps serving happily while all data quietly goes stale, which is a much less obvious failure than a 502:
  ```bash
  sudo docker compose ps          # expect hitchhiking-map AND hitchhiking-map-cron
  ```

### Testing sync / generate scripts (run in the container, not the host venv)
On the prod server the host `.venv` is minimal (only a few packages like `requests`) — the full dependency set lives inside the Docker image, so `flask ... generate <script>` will `ModuleNotFoundError` on the host. Test scripts inside the running container instead — use the **cron** container, which is where they run for real and which has the headroom (`show` alone peaks ~1.6 GB, against the web container's 2 GB cap):
```bash
sudo docker exec hitchhiking-map-cron /usr/local/bin/flask --app hitch generate <script>
```
Only `dist/`, `hitch/static/`, `hitch/templates/`, `db/`, and `logs/` are bind-mounted (see `docker inspect`). `hitch/scripts/` is **not** mounted — it's baked into the image at build time. So a new/edited script won't exist in the running container until the image is rebuilt; to test it before a rebuild, copy it in first (into whichever container you're running it in):
```bash
sudo docker cp hitch/scripts/<script>.py hitchhiking-map-cron:/app/hitch/scripts/<script>.py
```
Because `dist/` and `static/` **are** mounted, changes to generated JSON, `map.js` and `style.css` are picked up live without a rebuild — no restart needed, and `asset_url()` re-hashes on the next render so browsers don't serve a stale copy.

**Templates are the exception: mounted, but NOT live.** The production process runs with `TEMPLATES_AUTO_RELOAD` unset and `debug=False`, so `app.jinja_env.auto_reload` is `False` and each template is compiled once at boot and cached for the life of the process. An edit to `hitch/templates/*.html` is visible inside the container (`docker exec … grep`) while the served page still shows the old markup. **`sudo docker restart hitchhiking-map` is required** (a few seconds of 502). Watch for the half-applied state this creates: a change that spans a template and a static file goes live in two pieces, the JS/CSS immediately and the HTML only on restart.

Changes under `hitch/scripts/` and `deploy/cron.sh` require a rebuild/redeploy to take effect (including the cron entry that schedules the script).

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

**Changing a column's constraints is not an `ALTER`.** SQLite has no `ALTER TABLE ... ALTER COLUMN`, so relaxing a `NOT NULL` (or changing a type) needs the twelve-step table rebuild: create the new table, copy the rows, drop the old one, rename. `hitch/scripts/migrate_trip_user_nullable.py` is the worked example (it made `trip.user_id` nullable for anonymous auto-trips) — standalone stdlib script, idempotent, verifies the row count survived:
```bash
sudo docker exec hitchhiking-map python3 /app/hitch/scripts/migrate_trip_user_nullable.py --db /app/db/hitchhiking-prod.sqlite
```
**A whole new table needs a migration too.** `db.create_all()` only runs at `flask init`, which nothing on a deploy invokes, so a model added to `hitch/models.py` has no table in prod until someone creates it — and every route touching it 500s with `no such table: <name>`. `hitch/scripts/migrate_ride_images.py` is the worked example (it created `ride_image`): standalone stdlib script, literal `CREATE TABLE` kept in step with the model, idempotent.
```bash
sudo docker exec hitchhiking-map python3 /app/hitch/scripts/migrate_ride_images.py --db /app/db/hitchhiking-prod.sqlite
```

A plain added column has a one-liner example too: `hitch/scripts/migrate_recent_seen_at.py` (`user.recent_seen_at`, applied to prod on 2026-08-07) — same shape, `ALTER TABLE ... ADD COLUMN` guarded by a `PRAGMA table_info` check so re-running is a no-op.

Run the migration **before** pushing the code that depends on it: a deploy is a push, so the new code is live within a minute or two and would otherwise hit an `IntegrityError` on the old constraint (or a missing table).

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
   - **Fetching**: Every 5 minutes via `fetch_nostr_incremental.py` (only new/edited events, upserted; also applies NIP-09 deletions); a FULL re-fetch via `fetch_nostr.py` runs weekly to catch back-dated events and refresh the public exports
   - **Process Flow**:
     - Node.js script fetches events from relays - relays might contain new rides from other apps and also new rides from this app that were directly sent to the nostr relay on creation (because doing it natively in .ts is easier than in python). Two entry points: `src/index.ts` (full history → `dist/allPosts.json` + `.csv`, used by the nightly `fetch_nostr`) and `src/index_incremental.ts` (events since a `SINCE` timestamp → compact `dist/newPosts.json`, used by the 30-min `fetch_nostr_incremental`)
     - Python reads the JSON: `fetch_nostr.py` reads `dist/allPosts.json` and delete-and-recreates the whole table; `fetch_nostr_incremental.py` reads `dist/newPosts.json` and upserts by `(pubkey, d)`. Both parse content via the shared `parse_post_to_ride_fields`
     - Parses JSON content and extracts ride metadata (stops, signals, ratings, etc.)
     - the nostr events can contain information about rides that this project does not support yet, all information that is supported is stored in RideEvent, we aim incorporate all information from the nostr rides in the furture
     - Stores in `RideEvent` table (nightly full run recreates it; 30-min incremental upserts into it)
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

#### Core Sqlite Tables (see hitch/models.py for the database schema)
We use the sqlite tables as a canonical format to easily translate between the nostr data and the data we serve to the frontend via .json files and to store some that is not updated frequently information (e.g. about hitchwiki articles and osm).
**Tables Written by Application:**

- **`ride_event`**: All Nostr ride events
  - Full Nostr event structure (id, pubkey, sig, created_at, tags)
  - Parsed content fields: stops, signals, hitchhikers, rating, waiting_duration
  - Extracted coordinates: start lat/lon, destination lat/lon
  - User metadata: hitchhiker nicknames, submission times
  - **Written by**: `fetch_nostr.py` (full table delete/recreate, weekly), `fetch_nostr_incremental.py` (upsert by `(pubkey, d)` + NIP-09 deletions, every 5 min), and `main.py`'s `_store_published_ride` (same upsert, called synchronously right after this app publishes/edits a ride, so the row exists before the next fetch cron runs — see Ride Creation/Update Flow)
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

**Legacy Tables:**
- **`points`**, **`duplicates`**
  - Historical hitchmap.com data: `duplicates` is written by user duplicate reports (`main.py`, `to_sql("duplicates", ...)`), `points` backed the review-moderation queue (`user.py`).
  - **Neither table exists in `hitchhiking-prod.sqlite` any more** (verified 2026-07-28 — the DB has no `points` and no `duplicates`). Anything that reads them 500s: that is what killed `/contributors`, which is now a 301 to `/leaderboard`. `main.py`'s duplicate report survives only because pandas `to_sql(..., if_exists="append")` creates the table it writes to. `claim-review/<id>` (`user.py`) still reads `points` and will 500 — it is behind auth, so no crawler finds it, but do not assume the table is there.
  - There was a `sync_upstream.py` that pulled these (plus unused legacy `service_areas`/`road_islands`) from a nomadwiki.org dump daily; it was removed 2026-07-19 — the dump URL 404s (301s to the wiki home page) and the runtime routing tables are the singular `service_area`/`road_island` built from OSM by `sync_service_areas.py`/`sync_road_islands.py`, not these.

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
   - Shape: `{"spot": {name, wait, distance, osm_id, car_pooling, hitchwiki_article, hitchwiki_map}, "rides": [{id, rating, wait, comment, hitchhiker_name, submission_time, ride_datetime}, ...]}` — `spot` holds the click-time info slimmed out of spots.json (keys omitted when absent). `name` is the spot's display name (see `spot_names.py`); it lives here rather than in `spots.json` because ~30k name strings would add ~1 MB to the file every visitor downloads on map load
   - Fetched lazily by the frontend only when a marker is clicked (`map.js` handleMarkerClick merges `spot` into the marker data and re-renders the summary)
   - Each ride also carries `distance`, `arrival_datetime`, `no_ride`, and — omitted when the ride recorded neither, like `images` — `vehicle_kind` / `signal_methods`. Those last two exist so the spot pane can apply a vehicle or signal filter from its own data (see the filter section below) instead of pulling the multi-MB rides index; only ~2% of rides record a vehicle and ~20% a signal method, so shipping nulls would grow all ~37k files for nothing
   - The `by-spot` directory is wiped and rewritten on each `show.py` run so deleted spots don't leave stale files

4. **`spots_recent.json`** - Latest 1000 rides
   - Sorted by submission time (descending)
   - Used for tabular "Recent Rides" page
   - Includes ride URL, timestamp, username, rating, distance

5. **`races.json`** - Race standings for `/races`
   - A race is a city pair + timespan, defined in `RACES.md` at the repo root; `hitch/scripts/races.py` parses it and ranks the top 3 fastest hitchhikers per race (chains of consecutive rides, ≤10 km between legs, ≤20 km from the city centres — the file documents the full rule set)
   - Hardly any ride logs an arrival time, so a missing one is estimated from the leg distance at 75 km/h; affected entries are flagged `estimated` and the page says "partly estimated"
   - `races.py` is a pure library (no app context, no side effects) — `show.py` calls it, `/races` (`user.py`) only reads the JSON
   - Standings for *every* race are precomputed, but which races the page lists is decided per request by `races.current_races` (running now, or starting within the next month) so a race opens/closes on its own date rather than on the next cron run

6. **`heatmap.json`** - Predicted waiting times
   - Generated using sklearn Gaussian Process model
   - RGBA image overlay data (lat/lon bounds: -56 to 80, -180 to 180)
   - Legend with color boundaries for waiting time visualization
   - Can be disabled via `GENERATE_HEATMAP=False` config

7. **`generated_at.json`** - `{"ts": <epoch seconds>}`, the instant `show.py` took its DB snapshot
   - Captured as `snapshot_ts` before any table is read, but written last, so the file never claims a snapshot whose data isn't on disk yet
   - Read by `/pending_rides.json` (see below) to know which rides the generated files are still missing

8. **`spots.gpx`** (+ `.gz` sidecar) - every spot as a GPX 1.1 waypoint, ~33 MB / 7 MB gzipped, for the menu's "Download rides → As GPX" link
   - Built by `hitch/scripts/spots_gpx.py` (a pure library, called by `show.py` once `spots_data`/`spot_details` exist — kept out of `show.py` for the same reason as `spot_naming.py`: that module does all its work at import time, so nothing defined there can be imported or tested)
   - **Pre-generated rather than built in the browser.** The menu used to assemble it client-side from `allMarkers` via a CDN copy of `togpx`; the browser only ever holds `spots.json`, which has no spot name, waiting time or ride distance, so every description read "Waiting time: -" and no waypoint had a name. Each waypoint now carries the name, rating, ride count, typical wait/distance, last-ride date and the OSM / car-pooling / fuel / Hitchwiki links — as `<desc>` lines *and* as `<hw:spot>` extensions
   - **A waypoint is the whole spot page, comments included.** Under the summary the `<desc>` lists every ride at the spot the way the pane's cards read them (`map.js` `renderRideCards`): newest first, `date · wait · distance · rating — who`, the comment underneath, then any photo URLs (absolute — a site-relative one resolves against nothing inside an imported file). An offline map app is the *end* of the road for this file: there is no "see the rides on the website" tap to follow and often no network, so an averages-only waypoint drops the one thing people open a spot for. English weekday abbreviations, unlike everywhere else in the app — an exported file carries no language to resolve `translations/weekdays.py` against, and the rest of the description is English too. The clock time is printed only for a ride's own `ride_datetime`, never for the `submission_time` the date falls back to (that time of day is when someone typed the ride in)
   - **The rides are *not* mirrored into `<extensions>`** the way the per-user ride export mirrors a ride's Nostr content. Adding them doubled the file (33 → 70 MB, 7 → 12 MB gzipped) for a channel no map app renders and that `dist/rides/by-spot/<id>.json` already publishes as structured data. Capping rides per waypoint, on the other hand, buys nothing: the median spot has 1 ride and the largest has 83, so a cap of 5 would still keep 88% of the bytes
   - **Streamed a waypoint at a time** (`GpxStream`, `hitch/gpx.py`), never built as one tree: 35k waypoints of ElementTree objects is ~100 MB arriving at the very end of a run that already holds the whole ride table in pandas, and this host has been OOM-killed before. Written to `.tmp` and renamed so a download mid-regeneration never sees a half-written file
   - It is in `should_regenerate_json`'s file list despite not being JSON, so a deploy that adds it (or a `dist/` that lost it) regenerates instead of leaving the menu link 404ing until the next ride lands

**Note**: JSON regeneration is optimized - files are only rebuilt when database modification time is newer than existing JSON files (unless `--force` flag is used).

#### Files Generated by `why_not_hitchhike.py` (weekly)
- **`why_not_hitchhike.json`** — the whole `/why-not-hitchhike` page: `criteria` (the four thresholds, rendered on the page so the claim is never implicit), `coverage` (usable vs. indexed rides, duplicates collapsed — what the empty state prints), `matches` and `near_misses`. Each row is a spot → destination-cluster pattern with a Monday-first `weekday` **index** (never a name: 31 languages), ride/date counts, distance and wait summaries, and the individual rides behind it

#### Per-user export (`/me/downloads`, private)
The other half of the download story: a logged-in user's own rides, linked from their account page and from the menu. There is deliberately no `/account/<username>` counterpart — a person's full ride records are theirs to export, even though each ride is public on the map.
- **`/me/rides.gpx`** — built by `hitch/blueprints/utils/ride_gpx.py`. A ride with a recorded destination becomes a **`<rte>`** (pickup → destination); one without becomes a single **`<wpt>`**, because inventing an endpoint would draw a line on the user's map that no car ever drove. Waypoint/route names come from the same spot names the map shows, read out of `dist/rides/by-spot/<id>.json`
- **"all information about the ride" is the point**: a readable `<desc>` (rating, wait, times, distance, signals, vehicle, driver, give-up reasons, hitchhikers, source, licence, comment) *plus* the verbatim Nostr `content` mirrored into `<extensions>` under the `hw:` namespace, so fields this app has no UI for yet still survive the export
- **`/me/rides.json`** — the signed Nostr events as published, signature included, for anyone who wants to verify or re-import them
- Both are `Cache-Control: private, no-store`, and `sw.js` skips them (and `spots.gpx`) entirely: private data must not sit in a shared browser's cache after a logout, and a 33 MB file must not eat the offline map's storage quota

#### Ride photos (`dist/ride-images/`, uploaded not generated)
Up to **3 photos per ride**, added at the very bottom of the `/ride` form (both the new-ride and the `?edit=<d_tag>` variant) and displayed in a "Photos" section on `/ride/<d_tag>`. Code: `hitch/blueprints/utils/ride_images.py`, model `RideImage`.
- **Also surfaced on the spot pane** (`/spot/<spot_id>`) as a horizontally scrollable strip at the top, above the "Hitch here" buttons — a picture of the shoulder answers "is this spot any good" faster than the averages below it. `map.js` `renderSpotPhotos` flattens the photos of every ride at the spot in card order (newest ride first); each thumbnail links to `/ride/<d_tag>`, since a photo only means something next to the report it came with. The strip is `hidden` (not merely empty) when there are none: an empty flex row still costs its gap and padding on every one of the ~35k spots that has no photo. Data comes from `images` in `dist/rides/by-spot/<sid>.json` (`show.py` `get_ride_image_urls`, claimed photos only) **and** from `/pending_rides.json` (`_images_by_ride` → `ride_map_entry`), so a photo uploaded minutes ago doesn't trail its own ride card by a `show.py` cycle.
- **Not wired to Nostr, on purpose.** The hitchhiking data standard has no image field we could fill without inventing one, and a relay is the wrong place for binary payloads. The only link between a photo and its ride is `ride_image.ride_d_tag`, so photos survive an edit (which republishes the event under the same `d`) and can be attached to a ride imported from elsewhere. `RideEvent.images` is a column from the standard and stays untouched.
- **Every upload is decoded and re-encoded through Pillow** (max 1600 px, JPEG q82) rather than stored as received. That *is* the security model: the bytes served back are ones Pillow wrote, so a file that is simultaneously a valid image and a valid HTML/script payload cannot survive the round trip. It also strips EXIF — a phone photo carries GPS coordinates and a device serial, which someone photographing a slip road is not choosing to publish. `Image.MAX_IMAGE_PIXELS` is pinned to 50 Mpx against decompression bombs.
- **A photo is uploaded the moment it is picked, not on submit** — `POST /ride-image`, into a server-side draft keyed by a random `draft_token` the form holds in a hidden input; `POST /ride` then claims that draft onto the new `d` tag (`claim_draft_images`). Anything else loses pictures, and both failure modes were shipped once and reported: choosing a pickup location **navigates the whole page** to the map (`selectLocation`, which round-trips the form through sessionStorage) and no file input survives that; and re-opening the file picker **replaces the entire FileList**, so adding photos one at a time kept only the last. `GET /ride-image/draft/<token>` is how the form redraws its tiles after that navigation — it is under `/ride-image/`, not `/ride-images/`, because the plural prefix is the stored files served from `dist/` by `catch_all`. Unclaimed drafts are swept after `DRAFT_TTL` (24 h) opportunistically from the upload endpoint, so the feature needs no cron entry.
- **The cap is re-checked at claim time.** The token travels through the browser, so the number that finally matters is how many photos the *ride* has, not how many the draft was allowed.
- **UI is a strip of square tiles with a trailing dashed "+"** (Strava-style), each uploaded photo carrying a small × at its top right. A tile appears immediately from the local `URL.createObjectURL` preview and dims with an "Uploading…" overlay until the server answers, then swaps to the stored (rotated, EXIF-stripped) file — on a phone the upload takes seconds, and an empty slot reads as "nothing happened". The × deletes **immediately** via `POST /ride-image/<id>/delete`, keyed by the draft token for an unclaimed photo and by ride ownership for one already attached; deferring removal to submit cannot work, since the map navigation would drop the pending list.
- **Files live in `dist/`** because that directory is bind-mounted (uploads survive an image rebuild, and a deploy's `git reset --hard` cannot touch them), entirely gitignored (nothing a visitor uploads can reach the repo), and already served by `catch_all` — so nothing extra serves them. Layout is `dist/ride-images/<yyyy>/<mm>/<uuid>.jpg`; the uploaded filename is never reused (attacker-controlled, may collide, can itself carry personal data). `set_public_cache_headers` gives `/ride-images/*` a year of `immutable` caching, since a uuid URL's bytes can never change.
- **Licence:** photos are published under **CC BY-SA 4.0**, stated next to the upload tiles and again under the gallery, matching how comments/usernames are already licensed (the database as a whole stays ODbL).
- **Anonymous uploads are allowed**, because the ride form itself is. `ride_image.user_id` is then NULL and the abuse trail is the ride's row in `logs/ride_ips.csv` (`log_ride_ip`) — deliberately not an IP column, which would put personal data in the DB and its off-site backups.
- `MAX_CONTENT_LENGTH` (settings.py, 40 MB) is the outer guard on request size; without it any unauthenticated POST could make waitress buffer unbounded memory on a host the OOM killer has already visited.
- **Schema changes → run `hitch/scripts/migrate_ride_images.py` on prod before deploying** (see the migrations section; `db.create_all()` only runs at `flask init`). It both creates the table and rebuilds it for the draft columns. Applied to `hitchhiking-prod.sqlite` on 2026-07-26.

#### Live-from-DB endpoints (bypass `dist/` entirely)
A couple of routes in `main.py` read the database directly on every request instead of serving pre-generated files, because their whole purpose is to show something newer than the last `show.py` run:
- **`/proposed_spots.json`** - all `ProposedSpot` rows, newest first
- **`/pending_rides.json`** - rides with `created_at >=` the `generated_at.json` snapshot (falling back to `rides_index.json`'s mtime if that file doesn't exist yet, which under-returns rather than double-shows). Normally an empty array; `map.js` fetches it after `loadMarkers` and folds the rides into the map via `pending_rides.js` — bumping an existing marker's count/`latest_ms`/destinations, or drawing a brand-new marker for a spot with no ride in `spots.json` yet — so a ride is visible within moments of submission rather than after the next `show.py` pass

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
                                  dist/{spots,rides_index,spots_recent,heatmap,generated_at}.json
                                          + dist/rides/by-spot/<sid>.json
                                                              ↓
                                                        Map UI (map.js)
```

### Ride Creation/Update Flow

When a user submits a new ride or edits an existing one:

1. **Immediate**: Flask validates form data → publishes ride event directly to Nostr relays (synchronous, ~5 sec) → `_store_published_ride` (`main.py`) parses that same signed event with `parse_post_to_ride_fields` — the function both fetch scripts use — and upserts it into the local `RideEvent` table on `(pubkey, d)`, `created_at >=` (we are the publisher, so our copy is always at least as new) → returns redirect to `/#success`. This never raises: the ride is already on the relays by this point, so a local DB failure is logged and swallowed rather than turned into a 500 (a silently-rejected relay publish would then only be caught by the weekly full `fetch_nostr`, which drops what no fetch ever confirmed — the same gap `dist/temporary.json` exists to record). Because the row lands immediately, `/ride/<d_tag>` resolves and the ride shows on the author's profile at once, and an edit's new text is live immediately too — the cron steps below are how the *generated* map files (`spots.json`, `rides_index.json`, per-spot files) and `/pending_rides.json`'s fallback catch up, not how the ride reaches the DB.
   - Exception: co-hitchhiker records ARE written to the local `CoHitchhiker` table immediately, because co-hitchhiker acceptance is app-local state (not stored on Nostr). The submitter lists co-hitchhiker usernames, and each co-hitchhiker must accept via `/accept-co-hitchhiking-ride/<d_tag>` — this acceptance workflow only exists in the local DB.
   - For edits, the updated event is re-published to Nostr with the same `d_tag`
2. **up to ~5 min later**: `fetch_nostr_incremental` cron runs (every 5 min) → Node.js fetches only events newer than our newest ride (plus all kind-5 deletions) → Python upserts them into `RideEvent` by `(pubkey, d)` and applies deletions. For our own rides this is a no-op re-confirmation (the row is already there from step 1, `_store_published_ride`'s upsert lands the same fields the cron would); it's the only path by which rides published straight to the relay by other Nostr clients (not through this app's submit form) reach the local DB. A weekly full `fetch_nostr` still delete-and-recreates the whole table to catch back-dated events and refresh the public exports
3. **up to ~10 min later**: `show.py` cron (every 10 min) detects DB modification → regenerates `spots.json`, `rides_index.json`, etc. Until this runs, a just-submitted ride is on `/ride/<d_tag>` and the author's profile, but the map itself only shows it via `/pending_rides.json` (see Generated JSON Files)
4. **Ride appears on map** — the map itself picks the ride up via `/pending_rides.json` within moments of submission (see Generated JSON Files); the *generated* files catch up within ~10 minutes, at which point `/pending_rides.json` stops serving that ride (deduped by `show.py`'s `snapshot_ts`) and the marker/spot pane come from `spots.json` / the per-spot file instead

```
User submits form
    ↓ (immediate)
Flask → Nostr Relays (publish ride event)
    ↓ (immediate)
_store_published_ride → RideEvent table (upsert) — /ride/<d_tag> and the profile page work now
    ↓ (redirect to /#success)
    ...
    ↓ (up to ~5 min, cron)
fetch_nostr_incremental → Nostr Relays → dist/newPosts.json → RideEvent table (upsert, re-confirms our own rides; the only path for other sources)
    ↓ (up to ~10 min, cron)
show.py → dist/{spots,rides_index,spots_recent,heatmap,generated_at}.json
        → dist/rides/by-spot/<sid>.json (one file per spot, lazy-loaded)
    ↓
Map UI loads updated JSON → ride visible on map
```

In between steps 1 and 3, `/pending_rides.json` (served live from the DB, see Generated JSON Files) is what makes the ride visible on the map without waiting for the cron.

### In-ride tracker: end of a journey (`hitch/static/inride.js`)

The "Start hitchhiking" flow is the *other* contribution path (the `/ride` form is the first). One journey can log several rides — one per Finish, plus one for a Give Up — and they reach the server through a durable localStorage **outbox**, not a form POST. Two stores exist alongside it:

- **`inride.journeyLog`** — every ride *this* journey has logged, oldest first: `{id (outbox item id), dTag (filled in on upload), ride (share-card facts), at}`. Reset by `journeyFlow.start` (a new journey) but deliberately **not** by `nextRide` (a further leg of the same one). The d tag is written back here rather than kept in memory because a long hitch outlives the page — a locked phone reloads the PWA between legs, which would otherwise drop every already-uploaded leg from the trip.
- **`inride.pendingTrip`** — a finished multi-ride journey still owing its trip: `{entries: [{id, dTag|null}], createdAt}`. Durable because the rides may still be queued; a journey hitched through a dead zone must group itself once the phone reconnects, possibly days later. Dropped after 7 days.

**`finalizeJourney()` is the single close-out**, called by End Hitch, Give Up, cancelling a leg, and discarding a stale journey (that last one with `share: false`). Every exit runs it, because what the hitchhiker produced is the journey as a whole, not the leg they happened to stop on. It:

1. Opens **the same success overlay a past-ride submission gets** (`map.js` `showPostSubmitOverlay` / `showSuccessOverlay`), for the **last** ride logged. Anonymous journeys route through the one-time sign-up nudge exactly as `#success-anon` does.
2. Queues the auto-trip when the journey logged more than one ride.

Two things are worth knowing before editing this:

- **The share card's d tag is only knowable after the upload.** The client uuid pins just the *suffix* of the Nostr `d` (the server prefixes its source), so the real value arrives in the `/ride` reply. `showSuccessOverlay(opts)` therefore accepts `opts.dTag` as a **promise** — Give Up finalises the journey in the same breath as queueing the ride, and waiting on it before opening the overlay would leave the user staring at a bare map for the ~5 s of the Nostr publish. The wait sits behind the card's own "Drawing your ride…" status instead; after `DTAG_WAIT_MS` it settles for `null` and the card links to the map.
- **`POST /auto-trip`** (`user.py`) is fire-and-forget and idempotent: it returns the existing trip if any of the posted d-tags is already in one, so the client's retry can repeat it freely. It only groups recently published rides (`AUTO_TRIP_MAX_AGE_S`) that the caller may group — listed hitchhiker for a logged-in user, *no* named hitchhiker for an anonymous one, so a crafted POST can't bundle someone else's rides onto a trip page. The name is `"<start> → <end>, <Month Year>"` from Photon reverse geocoding, collapsing to one place or to `"Hitchhiking trip"` when that fails. **No `reverse_geocoder` fallback here** (unlike `route_preview.py`): it loads ~30 MB into the long-lived waitress workers, and this host has been OOM-killed before.

### Cron Schedule (deploy/cron.sh)
- **Every 5 minutes**: `fetch_nostr_incremental` - Fetch only new/edited rides from Nostr and upsert them + apply NIP-09 deletions (cheap; replaced the every-30-min full `fetch_nostr`)
- **Weekly (Mon 00:51)**: `fetch_nostr` - FULL Nostr re-fetch + table rebuild; catches back-dated events and refreshes the public `allPosts.json`/`.csv` exports (deletions are handled by the 5-min incremental job). **The minute must stay off a multiple of 5**: it shares `fetch_nostr.lockfile` with the `*/5` incremental job, and at 00:50 the two started in the same second and this one always lost `flock -n`, so it silently never ran for 11 days
- **Every 10 minutes**: `show` - Regenerate JSON map data
- **Daily at 1:30 AM**: prune `dist/dir/` route link-preview cache — plain `find -mtime +7 -delete`; previews regenerate on demand, the `dist/tiles` cache is not touched
- **Daily at 2 AM**: `build_ride_routes.py --skip-detailed` - Rebuild the routing graph (`dist/repeatable_routes.json`, `dist/oneoff_routes.json`, `dist/test_routes.json`). Not a `flask generate` script — cron calls the file directly with `python3`
- **Daily at 3 AM**: `sync_osm` - Sync OSM hitchhiking spots
- **Daily at 3:30 AM**: `sync_car_pooling` - Sync OSM car-pooling spots
- **Daily at 3:45 AM**: `sync_fuel` - Sync OSM fuel / gas stations near spots
- **Daily at 4 AM**: `sync_hitchwiki` - Sync Hitchwiki article coordinates
- **Daily at 4:15 AM**: `sync_events` - Sync Hitchwiki `Category:Events` into `dist/events.json`
- **Daily at 4:30 AM**: `spot_names.py` - Reverse-geocode street names for spots no OSM feature can name. Not a `flask generate` script — cron calls the file directly with `python3`. Runs after `show` because it reads `dist/spots.json`
- **Daily at 5 AM**: `dashboard` - Regenerate analytics dashboard
- **Daily at 5:30 AM**: `route_pages` - "Hitchhiking from X to Y" SEO pages. Must run **before** `cities`, which writes `sitemap.xml` and folds in `dist/route/index.json`
- **Daily at 6 AM**: `cities` - Regenerate per-city pages (all languages) + `sitemap.xml` + `robots.txt`
- **Daily at midnight**: `notify_nearby_hitchhikers` - Send nearby-hitchhiker notification emails
- **Weekly (Sun 1 AM)**: `backup_to_drive.py` - Scrubbed SQLite backup to Google Drive. Runs before the 2 AM routing rebuild so the two heaviest jobs don't overlap (the backup holds a full ~400 MB snapshot plus its gzip on disk)
- **Weekly (Mon 7 AM)**: `why_not_hitchhike` - Rebuild `/why-not-hitchhike`. Weekly, not nightly: the output only moves when a new ride arrives carrying a departure time, a destination *and* a wait together — a few dozen a week out of ~74k rides. Runs after `show` (reads `rides_index.json`), after `ride_places`/`spot_names` (which name its endpoints), and after the 6 AM `cities` run
- **Weekly (Mon 8 AM)**: `sync_hitchhiking_rides_dataset` - Push rides to the Hugging Face dataset
- **Monthly (1st, 9 AM)**: `country_ratings` - Regenerate country hitchability CSV + `country_ratings.json` / `country_insights.json`

(Several legacy jobs — `dump`, `fetch-roads`, `fetch-areas` — are commented out in `deploy/cron.sh`.)
