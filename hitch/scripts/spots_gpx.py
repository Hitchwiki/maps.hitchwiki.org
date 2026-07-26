"""Write dist/spots.gpx — every spot on the map, for the menu's "Download rides" link.

Pre-generated rather than assembled in the browser (which is what the menu used to do,
via a CDN copy of togpx): the client only ever holds spots.json, which carries neither
the spot's name nor its waiting time or ride distance — those live in the per-spot files
that are fetched one marker at a time. show.py is the only place all of it is in memory
at once, so it is the only place the export can be complete.

A pure library, called by `show.py` once it has built `spots_data` / `spot_details`.
Kept out of show.py for the same reason as spot_naming.py: that module does all of its
work at import time, so nothing defined there can be imported or tested on its own.
"""

import gzip
import os
import shutil

from hitch.gpx import GpxStream

SITE_URL = "https://maps.hitchwiki.org"

# Icon hint for importers that draw a symbol per waypoint (a Garmin symbol name, which
# is the de-facto vocabulary). An unrecognised name degrades to a default pin.
SPOT_SYM = "Flag, Blue"


def spot_waypoint(spot, detail, spot_id, last_ride=None):
    """One waypoint dict for a spot: `spot` is its spots.json entry, `detail` its
    per-spot detail (name / wait / distance / OSM links).

    Everything we hold about the spot goes in twice: as `<desc>` lines for importers
    that only show text, and as structured `<extensions>` for anything that can read
    them. `last_ride` is a preformatted date (show.py holds the timestamp).
    """
    rating = spot.get("rating")
    has_rating = rating is not None and rating == rating  # NaN is the only value != itself
    osm_id = detail.get("osm_id")
    car_pooling = detail.get("car_pooling") or {}
    fuel = detail.get("fuel") or {}

    lines = [
        f"Rating: {rating:.1f}/5" if has_rating else None,
        f"Rides logged: {spot['review_count']}",
        f"Typical wait: {detail['wait']} min" if detail.get("wait") is not None else None,
        f"Typical ride: {detail['distance']} km" if detail.get("distance") is not None else None,
        f"Last ride: {last_ride}" if last_ride else None,
        f"Official hitchhiking spot: https://www.openstreetmap.org/node/{osm_id}" if osm_id else None,
        f"Car pooling spot: https://www.openstreetmap.org/{car_pooling['osm_type']}/{car_pooling['id']}" if car_pooling else None,
        f"Gas station: https://www.openstreetmap.org/{fuel['osm_type']}/{fuel['id']}" if fuel else None,
        f"Hitchwiki: {detail['hitchwiki_article']}" if detail.get("hitchwiki_article") else None,
        f"Hitchwiki (area): {detail['hitchwiki_map']}" if detail.get("hitchwiki_map") else None,
    ]

    extensions = {
        "rating": round(float(rating), 2) if has_rating else None,
        "rides": spot["review_count"],
        "wait_minutes": detail.get("wait"),
        "distance_km": detail.get("distance"),
        "last_ride": last_ride,
        "osm_node": osm_id,
        "car_pooling": True if car_pooling else None,
        "gas_station": True if fuel else None,
        "hitchwiki_article": detail.get("hitchwiki_article"),
    }

    return {
        "lat": spot["lat"],
        "lon": spot["lon"],
        # The spot's real name where we have one. A list of 35k bare coordinates is
        # useless in an offline map's waypoint list, so fall back to the ride count.
        "name": detail.get("name") or f"Hitchhiking spot ({spot['review_count']} rides)",
        "desc": "\n".join(line for line in lines if line),
        "type": "hitchhiking",
        "sym": SPOT_SYM,
        "link": {"href": f"{SITE_URL}/spot/{spot_id}", "text": "This spot on Hitchwiki Maps"},
        "extensions": {"spot": {k: v for k, v in extensions.items() if v is not None}},
    }


def write_spots_gpx(path, waypoints, spot_count, generated_at):
    """Stream `waypoints` (an iterable of waypoint dicts) into `path` plus its .gz sidecar.

    Streamed a waypoint at a time rather than built as one tree: 35k waypoints of
    ElementTree objects would add ~100 MB right at the end of a show.py run that already
    holds the whole ride table in pandas, and this host has been OOM-killed before (see
    CLAUDE.md). Nothing here accumulates, so memory is flat in the number of spots.
    """
    # Written to a temp file and renamed: the menu links straight at this path, and a
    # visitor downloading while this runs must not get a half-written document.
    with (
        open(path + ".tmp", "wb") as fileobj,
        GpxStream(
            fileobj,
            name="Hitchhiking spots — Hitchwiki Maps",
            desc=(
                f"{spot_count} hitchhiking spots with community ratings, typical waiting times "
                "and ride distances. Generated from the Hitchwiki Maps ride database."
            ),
            link={"href": f"{SITE_URL}/", "text": "Hitchwiki Maps"},
            time=generated_at,
            keywords="hitchhiking, hitchhiking spots, Hitchwiki Maps",
        ) as stream,
    ):
        for wpt in waypoints:
            stream.waypoint(wpt)

    os.replace(path + ".tmp", path)
    # Precompressed sidecar, same deal as write_json_file: catch_all serves it with
    # Content-Encoding: gzip so the proxy doesn't recompress several MB of XML on every
    # download. Copied in chunks, and written after the plain file so its mtime is never
    # the older of the two (the route refuses a sidecar older than what it encodes).
    with open(path, "rb") as plain, gzip.open(path + ".gz.tmp", "wb", compresslevel=9) as compressed:
        shutil.copyfileobj(plain, compressed)
    os.replace(path + ".gz.tmp", path + ".gz")
    return os.path.getsize(path)
