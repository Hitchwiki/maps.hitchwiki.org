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
- **fetch_osm_*.py**: OSM data synchronization

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