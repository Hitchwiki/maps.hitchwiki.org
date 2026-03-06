# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Environment Setup
- **Virtual Environment**: `python3 -m venv .venv && source .venv/bin/activate`
- **Install Dependencies**: `pip install -r requirements.txt`
- **Database Setup**: `curl https://hitchmap.com/dump.sqlite > db/points.sqlite && curl https://hitchmap.com/dump.sqlite > db/prod-points.sqlite`
- **Configuration**: `cp example.env .env` (then set missing env variables)

### Flask Commands
- **Initialize Database**: `flask init` - Creates tables and default roles, runs generate-all
- **Run Server**: `flask run` - Starts development server
- **Execute Script**: `flask generate <script_name>` - Runs scripts from hitch/scripts/
- **Run All Scripts**: `flask generate-all` - Executes fetch_nostr and show scripts

### Code Quality
- **Linting**: `ruff check` - Code linting with line length 130
- **Formatting**: `ruff format` - Auto-format code
- **Pre-commit**: Uses ruff for linting and formatting via pre-commit hooks

## Architecture Overview

### Core Structure
- **Flask Application**: Main app factory in `hitch/__init__.py` with blueprint registration
- **Database Models**: SQLAlchemy models in `hitch/models.py` including User, RideEvent, OsmHitchhikingSpot
- **Blueprints**: 
  - `main` - Map rendering, experience logging, ride submission
  - `user` - User management and authentication
  - `publish_ride` - Ride publishing to Nostr protocol
- **Extensions**: Flask-Security for auth, Flask-SQLAlchemy for DB, Flask-Mailman for email

### Key Models
- **RideEvent**: Stores Nostr ride events with JSON content and extracted columns
- **OsmHitchhikingSpot**: OpenStreetMap hitchhiking locations
- **HitchwikiArticleLocation**: Hitchwiki article coordinates
- **CoHitchhiker**: Co-hitchhiker acceptance tracking

### Data Processing Scripts (hitch/scripts/)
- **fetch_nostr.py**: Fetches ride data from Nostr relays (runs every 10min via cron)
- **show.py**: Generates map data views (runs every minute via cron)
- **dashboard.py**: Analytics dashboard generation
- **dump.py**: Database export functionality
- **sync_osm.py**: OSM data synchronization (fetches highway=hitchhiking spots)
- **sync_hitchwiki.py**: Hitchwiki article synchronization (extracts coordinates from wiki articles)

### Configuration
- **Environment-based**: Development/Production/Testing configs in `settings.py`
- **Database**: SQLite with configurable paths via DATABASE_URI
- **Security**: Flask-Security with username-based auth, password hashing
- **Email**: SMTP2GO integration for user communication

### Deployment
- **Docker**: Dockerfile and docker-compose.yml for containerization
- **Cron**: Automated data fetching via `cron.sh` with file locking
- **Static Files**: Served from dist/ directory, includes PWA manifest
- **Web Server**: Waitress for production, Apache/NGINX reverse proxy configs provided

## Data Flow and Storage

### Data Sources
The application aggregates hitchhiking data from multiple sources:

1. **Nostr Protocol Network** (Primary ride data source)
   - **Source**: Decentralized Nostr relays (relay.nomadwiki.org, relay.trustroots.org, nos.lol)
   - **Data Type**: Hitchhiking ride events (Nostr event kind 34242)
   - **Fetching**: Every 10 minutes via `fetch_nostr.py`
   - **Process Flow**:
     - Node.js script (`hitch/scripts/fetch_hitchhiking_events/src/index.ts`) fetches events from relays
     - Writes raw events to `dist/allPosts.json` and `dist/allPosts.csv`
     - Python script (`fetch_nostr.py`) reads `dist/allPosts.json`
     - Parses JSON content and extracts ride metadata (stops, signals, ratings, etc.)
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
   - **Purpose**: Link rides to relevant wiki articles about hitchhiking locations

### Database Storage (SQLite)

**Primary Database**: `db/points.sqlite` (configured via `DATABASE_URI` in `settings.py:46-47`)
- **Location**: `db/` directory (relative to project root)
- **Default name**: `points.sqlite` (dev), `prod-points.sqlite` (production via `DATABASE_NAME` env var)
- **Path resolution**: `{project_root}/db/{DATABASE_NAME}`

#### Database Initialization
The database must exist before the application can run. Two initialization paths:

1. **Fresh Start**: `flask init` (`hitch/__init__.py:55-70`)
   - Creates all tables via `db.create_all()`
   - Creates default roles (admin, monitor, user, reader)
   - Runs `flask generate-all` to populate initial data
   - Tables are created from models in `hitch/models.py`

2. **Production Setup**: Download pre-populated database
   - `curl https://hitchmap.com/dump.sqlite > db/points.sqlite`
   - Contains historical ride data from legacy hitchmap.com
   - Can be synced with upstream via `sync_upstream.py` (daily at 7 AM)

#### Core Sqlite Tables

**Tables Written by Application:**

- **`ride_event`**: All Nostr ride events
  - Full Nostr event structure (id, pubkey, sig, created_at, tags)
  - Parsed content fields: stops, signals, hitchhikers, rating, waiting_duration
  - Extracted coordinates: start lat/lon, destination lat/lon
  - User metadata: hitchhiker nicknames, submission times
  - **Written by**: `fetch_nostr.py:33-74` (full table delete/recreate every 10 min)
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
  - **Read by**: Not currently queried (future feature)

**Legacy Tables (from upstream sync):**
- **`points`**, **`duplicates`**, **`service_areas`**, **`road_islands`**
  - Synced from hitchmap.com dump via `sync_upstream.py:23-28,97-132`
  - Used for routing and legacy data compatibility
  - Read by: `show.py:57` (via pandas `read_sql`), `main.py:253` (duplicate reporting)

### Generated JSON Files

**Location**: `dist/` directory (relative to project root)
- **Path resolution**: `{project_root}/dist/` (`helpers.py:89-101`)
- **Served by**: Flask at `/<path>` routes (`__init__.py:127-129`)

#### Files Generated by `fetch_nostr.py` (via Node.js script)
- **`allPosts.json`** - Raw Nostr events in JSON format
- **`allPosts.csv`** - Raw Nostr events in CSV format

#### Files Generated by `show.py`
The `show.py` script runs every minute and generates map data files from the database:

1. **`spots.json`** - Aggregated hitchhiking spots
   - Groups rides by exact lat/lon coordinates
   - Calculates: average rating, waiting time, ride distance
   - Includes: ride count, user lists, destination coordinates
   - Links to nearby OSM spots and Hitchwiki articles (within 100m)
   - Structure: `{id, lat, lon, rating, wait, distance, ride_count, osm_id, hitchwiki_article}`

2. **`rides.json`** - Individual ride records
   - Complete ride details for sidebar display
   - Links rides to spots via coordinate-based spot_id
   - Includes formatted HTML text for popups
   - Structure: `{id, spot_id, lat, lon, rating, wait, comment, hitchhiker_name, ride_datetime}`

3. **`spots_recent.json`** - Latest 1000 rides
   - Sorted by submission time (descending)
   - Used for tabular "Recent Rides" page
   - Includes ride URL, timestamp, username, rating, distance

4. **`heatmap.json`** - Predicted waiting times
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
                                          dist/{spots,rides,heatmap}.json
                                                              ↓
                                                        Map UI (map.js)
```

### Cron Schedule (cron.sh)
- **Every 10 minutes**: `fetch_nostr` - Fetch new rides from Nostr
- **Every minute**: `show` - Regenerate JSON map data
- **Daily at 7 AM**: `sync_upstream` - Upstream data synchronization
