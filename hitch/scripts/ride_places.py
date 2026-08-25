"""Reverse-geocode ride endpoints into place names, offline and incrementally.

Fills the `ride_place` table: one row per ride `d` tag, holding the origin and
destination place names plus their ISO country codes.

    d_tag | from_place | from_cc | to_place     | to_cc
    ------+------------+---------+--------------+------
    abc   | Metzeral   | FR      | Schweighofen | DE

Consumed by the account modal (#106) and, via show.py, by every ride the map renders.

Three decisions worth knowing:

**Why a cron script, not a request.** `reverse_geocoder` costs ~150 MB resident once its
index builds (measured). Loading that into every waitress worker on a host the OOM killer
has already visited (CLAUDE.md) is not worth a city name. Here it is one transient
process; queries are ~0.1 ms once warm, so the whole corpus resolves in a single batch.

**Why its own table, not columns on ride_event.** fetch_nostr deletes and rebuilds
ride_event wholesale every 30 minutes. Place names stored there would be destroyed twice
an hour and re-geocoded from nothing.

**Why not a JSON blob in dist/.** At ~70 000 rides that file is ~7 MB, and any process
reading it holds ~33 MB of parsed dict. A table lets a request look up the handful of
d_tags it actually needs.

Only rides missing from the table are geocoded, so steady-state runs are nearly free.
Names prefer the populated place (`name`), falling back to the administrative division
(`admin1`, e.g. "Berlin", "Lombardy") and finally the country code, so a ride in the
middle of nowhere still gets a meaningful label.
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

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS ride_place (
    d_tag      VARCHAR(255) PRIMARY KEY,
    from_place VARCHAR(255),
    from_cc    VARCHAR(2),
    to_place   VARCHAR(255),
    to_cc      VARCHAR(2)
)
"""


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
    conn.execute(CREATE_TABLE)
    conn.commit()

    known = {row[0] for row in conn.execute("SELECT d_tag FROM ride_place")}
    rows = conn.execute("SELECT d, content FROM ride_event WHERE d IS NOT NULL").fetchall()

    # Collect every point once, remembering which ride slot it belongs to, so the whole
    # backlog resolves in a single query. Rides already geocoded are skipped: a ride's
    # coordinates never change (an edit republishes under the same d tag, and the map
    # only ever gains rides), so a row once written stays correct.
    points, slots = [], []
    for row in rows:
        if row["d"] in known:
            continue
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
        logger.info("Nothing new to geocode (%d rides already resolved).", len(known))
        conn.close()
        return

    logger.info("Reverse-geocoding %d points for %d new rides", len(points), len({d for d, _ in slots}))
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

    conn.executemany(
        "INSERT OR REPLACE INTO ride_place (d_tag, from_place, from_cc, to_place, to_cc) VALUES (?, ?, ?, ?, ?)",
        [(d_tag, e.get("from"), e.get("from_cc"), e.get("to"), e.get("to_cc")) for d_tag, e in places.items()],
    )
    conn.commit()
    logger.info("Wrote %d ride_place rows (%d total)", len(places), len(known) + len(places))
    conn.close()


# Run on import: `flask generate` executes scripts by importing their module (see the
# generate command in hitch/__init__.py), matching show.py and cities.py. A
# `if __name__ == "__main__"` guard would make `flask generate ride_places` — used by the
# one-time backfill and the daily 04:45 cron — a silent no-op.
main()
