"""Reverse-geocode every ride's endpoints into place names, offline.

Writes dist/ride_places.json:

    {"<d_tag>": {"from": "Metzeral", "from_cc": "FR", "to": "Mitte", "to_cc": "DE"}, ...}

Used by the account modal (issue #106) to label a ride "Metzeral → Mitte" instead of
showing bare coordinates.

Why a cron script rather than doing this in the request:
`reverse_geocoder` costs ~150 MB resident once its index is built. Loading that into
every waitress worker on a host the OOM killer has already visited (see CLAUDE.md) is
not worth a place name. Here the cost is one transient process, and the app only ever
reads a small JSON file — the same shape as show.py / country_ratings.py.

Names prefer the populated place (`name`), falling back to the administrative division
(`admin1`, e.g. "Berlin", "Lombardy") and finally the country code, so a ride in the
middle of nowhere still gets a meaningful label.

Rides are geocoded in ONE batched rg.search call: the index build dominates, and a
single query for 20 000 points costs about the same as a query for one.
"""

import json
import logging
import os
import sqlite3

import reverse_geocoder as rg

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Resolve the DB path the same way hitch/settings.py does: db/{DATABASE_NAME}.
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATABASE_NAME = os.getenv("DATABASE_NAME", "hitchhiking-prod.sqlite")
DATABASE_URI = os.getenv("DATABASE_URI", os.path.join(BASE_DIR, "db", DATABASE_NAME))
DIST_DIR = os.path.join(BASE_DIR, "dist")
OUTPUT_JSON = os.path.join(DIST_DIR, "ride_places.json")

# Matches show.py / country_ratings.py: a "destination" closer than this is treated as
# no destination at all, so we don't label a ride "Berlin → Berlin".
MIN_RIDE_DISTANCE_KM = 1


def _label(hit):
    """Populated place, else administrative division, else country."""
    return (hit.get("name") or hit.get("admin1") or hit.get("cc") or "").strip() or None


def _country(hit):
    """ISO 3166-1 alpha-2, which the client turns into a flag emoji."""
    return (hit.get("cc") or "").strip().upper() or None


def _coords_from_stops(stops):
    """(pickup, destination) as (lat, lon) pairs; destination is None when absent."""
    if not stops:
        return None, None

    def point(stop):
        loc = (stop or {}).get("location") or {}
        lat, lon = loc.get("latitude"), loc.get("longitude")
        return (float(lat), float(lon)) if lat is not None and lon is not None else None

    pickup = point(stops[0])
    destination = point(stops[-1]) if len(stops) > 1 else None
    return pickup, destination


def main():
    conn = sqlite3.connect(DATABASE_URI)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT d, content FROM ride_event WHERE d IS NOT NULL").fetchall()
    conn.close()

    # Collect every point once, remembering which ride slot it belongs to, so the whole
    # corpus resolves in a single query.
    points, slots = [], []
    for row in rows:
        try:
            content = json.loads(row["content"]) if isinstance(row["content"], str) else (row["content"] or {})
        except (TypeError, ValueError):
            continue
        pickup, destination = _coords_from_stops(content.get("stops"))
        if pickup:
            points.append(pickup)
            slots.append((row["d"], "from"))
        if destination:
            points.append(destination)
            slots.append((row["d"], "to"))

    if not points:
        logger.info("No ride coordinates to geocode.")
        os.makedirs(DIST_DIR, exist_ok=True)
        with open(OUTPUT_JSON, "w") as f:
            json.dump({}, f)
        return

    logger.info("Reverse-geocoding %d points across %d rides", len(points), len(rows))
    hits = rg.search(points, mode=1, verbose=False)

    places = {}
    for (d_tag, slot), hit in zip(slots, hits):
        label = _label(hit)
        if label:
            entry = places.setdefault(d_tag, {})
            entry[slot] = label
            country = _country(hit)
            if country:
                entry[slot + "_cc"] = country

    # "Berlin → Berlin" says nothing; drop the destination when it repeats the origin.
    for entry in places.values():
        if entry.get("to") and entry.get("to") == entry.get("from"):
            entry.pop("to")
            entry.pop("to_cc", None)

    os.makedirs(DIST_DIR, exist_ok=True)
    with open(OUTPUT_JSON, "w") as f:
        json.dump(places, f)
    logger.info("Wrote %s (%d rides)", OUTPUT_JSON, len(places))


if __name__ == "__main__":
    main()
