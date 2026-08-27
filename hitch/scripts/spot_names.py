"""Reverse-geocode hitchhiking spots into street names, incrementally and resumably.

Fills the `spot_name` table: one row per spot id, holding the label `show.py` falls back
to when no OSM feature (official spot, service area, fuel station, car-pooling point)
can name the spot.

    spot_id            | name                    | lat      | lon
    -------------------+-------------------------+----------+---------
    52.30217_13.01991  | An der A10, Michendorf  | 52.30217 | 13.01991

Only 5,520 of 35,140 spots have any OSM feature within 100 m, so this is the common
case rather than a fallback for oddities.

Three decisions worth knowing:

**Why a standalone script, not part of show.py.** show.py runs every 10 minutes; this
one makes a network request per spot at 1 req/s against a third party. The two cannot
share a schedule. Same split, and same reasoning, as ride_places.py.

**Why the spot list comes from dist/spots.json, not the database.** That file is the
canonical post-merge set of spots, and its coordinates are exactly the ones the spot id
is derived from. Reading the ride table instead would name pre-merge coordinates that no
marker on the map corresponds to. It does mean this script depends on `show` having run,
the same dependency sync_fuel already has.

**Why a failed request stores nothing.** A row with a NULL name means "Photon answered
and had nothing to offer", and is never asked again. If a timeout wrote that same row,
one outage would permanently mark thousands of spots unnameable with nothing to
distinguish them from genuinely nameless ones.

Usage:
    python3 hitch/scripts/spot_names.py [--limit N] [--dry-run] [--db PATH]

--limit caps one run (default 2000, ~33 min at 1 req/s) so a cron run stays bounded;
--limit 0 is unlimited, for the initial backlog under nohup.
"""

import argparse
import json
import logging
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone

import requests

if __package__:
    from hitch.scripts.map_revision import mark_map_data_dirty
else:
    from map_revision import mark_map_data_dirty

# Resolve the DB path the same way hitch/settings.py does: db/{DATABASE_NAME}.
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# Run as a plain script (`python3 hitch/scripts/spot_names.py`), so the project root is
# not on sys.path — only the script's own directory is. Put it there before importing
# the shared naming library. The other standalone scripts here import nothing from
# `hitch`, which is why none of them needs this.
sys.path.insert(0, BASE_DIR)

from hitch.scripts.spot_naming import photon_label  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
logger = logging.getLogger(__name__)

DATABASE_NAME = os.getenv("DATABASE_NAME", "hitchhiking-prod.sqlite")
DATABASE_URI = os.getenv("DATABASE_URI", os.path.join(BASE_DIR, "db", DATABASE_NAME))
SPOTS_JSON = os.path.join(BASE_DIR, "dist", "spots.json")

PHOTON_URL = "https://photon.komoot.io/reverse"
USER_AGENT = "hitchwiki-maps/1.0 (+https://maps.hitchwiki.org)"
REQUEST_TIMEOUT_S = 10

# Photon is a free public service run by komoot. One request per second is the rate the
# rest of this codebase already holds itself to against third-party APIs.
REQUEST_INTERVAL_S = 1.0

# Bounded so a nightly cron run cannot turn into an 8-hour job. The ~30k initial backlog
# is meant to be drained by one manual `--limit 0` run.
DEFAULT_LIMIT = 2000

COMMIT_EVERY = 100

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS spot_name (
    spot_id     VARCHAR(64) PRIMARY KEY,
    name        VARCHAR(255),
    lat         REAL NOT NULL,
    lon         REAL NOT NULL,
    geocoded_at VARCHAR(32) NOT NULL
)
"""


def ensure_table(conn):
    """Create spot_name if absent. There is no migration framework in this project."""
    conn.execute(CREATE_TABLE)
    conn.commit()


def load_spots(path):
    """[(spot_id, lat, lon)] from a spots.json file.

    The id is built exactly as show.py's generate_spot_id and the map's
    `lat.toFixed(5)_lon.toFixed(5)` do, so a cached name and the per-spot file that
    consumes it always agree.
    """
    with open(path) as f:
        spots = json.load(f)
    out = []
    for spot in spots:
        lat, lon = spot.get("lat"), spot.get("lon")
        if lat is None or lon is None:
            continue
        out.append((f"{round(lat, 5):.5f}_{round(lon, 5):.5f}", lat, lon))
    return out


def pending(conn, spots):
    """The spots with no row yet — the only ones worth a request."""
    known = {row[0] for row in conn.execute("select spot_id from spot_name")}
    return [spot for spot in spots if spot[0] not in known]


def geocode(lat, lon, get=requests.get):
    """(answered, name) for one coordinate.

    `answered` distinguishes "Photon replied, and this place has no street" (True, None)
    from "we never got a reply" (False, None) — only the former may be cached.
    """
    try:
        response = get(
            PHOTON_URL,
            params={"lat": lat, "lon": lon, "lang": "en", "limit": 1},
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT_S,
        )
        response.raise_for_status()
        features = response.json().get("features") or []
    except (requests.RequestException, ValueError, AttributeError):
        return False, None
    if not features:
        return True, None
    return True, photon_label(features[0].get("properties") or {})


def resolve_pending(conn, spots, get=requests.get, limit=DEFAULT_LIMIT, delay=REQUEST_INTERVAL_S, dry_run=False):
    """Geocode the spots not yet cached, writing as we go. Returns a summary dict."""
    todo = pending(conn, spots)
    if limit:
        todo = todo[:limit]
    counts = {"named": 0, "unnamed": 0, "failed": 0, "total": len(todo)}

    for index, (spot_id, lat, lon) in enumerate(todo):
        if delay and index:
            time.sleep(delay)
        answered, name = geocode(lat, lon, get=get)
        if not answered:
            counts["failed"] += 1
            continue
        counts["named" if name else "unnamed"] += 1
        if dry_run:
            logger.info(f"{spot_id} -> {name}")
            continue
        conn.execute(
            "INSERT OR REPLACE INTO spot_name (spot_id, name, lat, lon, geocoded_at) VALUES (?, ?, ?, ?, ?)",
            (spot_id, name, lat, lon, datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
        # Commit as we go: at 1 req/s a full run is hours long, and an interrupted one
        # must resume rather than start over.
        if (index + 1) % COMMIT_EVERY == 0:
            conn.commit()

    if not dry_run:
        conn.commit()
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="max spots to geocode (0 = unlimited)")
    parser.add_argument("--dry-run", action="store_true", help="print resolved names without writing")
    parser.add_argument("--db", default=DATABASE_URI, help="path to the SQLite database")
    parser.add_argument("--spots", default=SPOTS_JSON, help="path to spots.json")
    args = parser.parse_args()

    if not os.path.isfile(args.spots):
        raise SystemExit(f"{args.spots} not found — run `flask generate show` first")

    spots = load_spots(args.spots)
    conn = sqlite3.connect(args.db)
    try:
        ensure_table(conn)
        outstanding = len(pending(conn, spots))
        logger.info(f"{len(spots)} spots, {outstanding} without a cached name")
        counts = resolve_pending(conn, spots, limit=args.limit, dry_run=args.dry_run)
    finally:
        conn.close()

    if not args.dry_run and counts["named"] + counts["unnamed"]:
        mark_map_data_dirty(os.path.dirname(os.path.abspath(args.spots)))

    logger.info(
        f"Geocoded {counts['total']} spots: {counts['named']} named, "
        f"{counts['unnamed']} with no usable place, {counts['failed']} failed (will retry). "
        f"{outstanding - counts['named'] - counts['unnamed']} left."
    )


if __name__ == "__main__":
    main()
