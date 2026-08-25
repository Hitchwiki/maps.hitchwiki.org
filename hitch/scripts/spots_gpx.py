"""Write dist/spots.gpx — every spot on the map, for the menu's "Download rides" link.

Pre-generated rather than assembled in the browser (which is what the menu used to do,
via a CDN copy of togpx): the client only ever holds spots.json, which carries neither
the spot's name nor its waiting time, ride distance or comments — those live in the
per-spot files that are fetched one marker at a time. show.py is the only place all of
it is in memory at once, so it is the only place the export can be complete.

A waypoint carries the whole spot page, comments included, not just the spot's averages:
the file is imported into offline map apps, where opening a spot is the *end* of the
road — there is no "see the rides on the website" tap to follow, and often no network.

A pure library, called by `show.py` once it has built `spots_data` / `spot_details`.
Kept out of show.py for the same reason as spot_naming.py: that module does all of its
work at import time, so nothing defined there can be imported or tested on its own.
"""

import gzip
import os
import shutil
from datetime import date

from hitch.gpx import GpxStream

SITE_URL = "https://maps.hitchwiki.org"

# Icon hint for importers that draw a symbol per waypoint (a Garmin symbol name, which
# is the de-facto vocabulary). An unrecognised name degrades to a default pin.
SPOT_SYM = "Flag, Blue"

# English weekday abbreviations, Monday-first (`date.weekday()`). Which day of the week
# a ride happened is a hitchhiking fact of its own (a Sunday service area is a different
# place than a Tuesday one, see CLAUDE.md), but an exported file carries no language to
# resolve hitch/translations/weekdays.py against — and every other word in this
# description is English too.
WEEKDAY_ABBR = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def _format_stamp(stamp, with_clock=True):
    """`"Sat 2026-08-01 11:32"` from a ride timestamp, or None if it isn't one.

    Only the leading `YYYY-MM-DD` decides the weekday, never any offset the stamp
    carries: it is already the ride's own local wall-clock time, and re-interpreting it
    would move a ride logged near midnight onto the wrong day (same rule as
    `with_weekday`).
    """
    text = str(stamp or "")
    try:
        weekday = WEEKDAY_ABBR[date.fromisoformat(text[:10]).weekday()]
    except ValueError:
        return None
    clock = text[11:16]
    has_clock = with_clock and len(clock) == 5 and clock[2] == ":"
    return f"{weekday} {text[:10]}" + (f" {clock}" if has_clock else "")


def _number(value):
    """A stat as the map prints it: whole kilometres/minutes, no trailing ".0"."""
    return f"{round(float(value)):g}"


def ride_lines(ride):
    """One ride written the way the spot pane draws its card.

    Same facts in the same order as `map.js` `renderRideCards` — no-ride badge, date,
    wait, distance, rating, who, then the comment underneath — because the point of
    exporting them at all is that a spot opened from this file in an offline map reads
    like the spot page it came from. Photo URLs follow, since an offline reader has no
    other way of learning the pictures exist; the remaining fields (arrival, vehicle,
    signals, ride id) are in the ride's `<extensions>` instead, so nothing is dropped.
    """
    rating, wait, distance = ride.get("rating"), ride.get("wait"), ride.get("distance")
    departure = ride.get("ride_datetime")
    # The clock time is printed only when it is the ride's own: the pane falls back to
    # the submission stamp for the date but never shows its time of day, which is when
    # someone typed the ride in, often weeks later.
    when = _format_stamp(departure) if departure else _format_stamp(ride.get("submission_time"), with_clock=False)
    meta = " · ".join(
        bit
        for bit in (
            when,
            f"{_number(wait)} min wait" if wait is not None else None,
            f"{_number(distance)} km" if distance is not None else None,
            f"{_number(rating)}/5" if rating else None,
        )
        if bit
    )
    # "Anonymous" is the sentinel the whole codebase uses for an unattributed ride, so a
    # missing name prints as that rather than as an empty author.
    who = ride.get("hitchhiker_name") or "Anonymous"
    head = f"{meta} — {who}" if meta else who
    if ride.get("no_ride"):
        head = f"No ride · {head}"

    lines = [head]
    comment = (ride.get("comment") or "").strip()
    if comment:
        lines.append(comment)
    # Absolute: the per-spot files store photo URLs site-relative, which resolves against
    # nothing once the file has been imported into a map app.
    lines.extend(f"Photo: {_absolute(url)}" for url in ride.get("images") or [])
    return lines


def _absolute(url):
    return f"{SITE_URL}{url}" if str(url).startswith("/") else url


def sort_rides(rides):
    """Newest ride first, by submission time falling back to the ride's own datetime —
    the order `handleMarkerClick` sorts the spot pane into, so the exported list and the
    web page agree on which ride is at the top."""
    return sorted(rides, key=lambda r: str(r.get("submission_time") or r.get("ride_datetime") or ""), reverse=True)


def spot_waypoint(spot, detail, spot_id, last_ride=None, rides=None):
    """One waypoint dict for a spot: `spot` is its spots.json entry, `detail` its
    per-spot detail (name / wait / distance / OSM links), `rides` the spot's entries
    from `dist/rides/by-spot/<spot_id>.json`.

    The spot's own facts go in twice: as `<desc>` lines for importers that only show
    text, and as structured `<extensions>` for anything that can read them. The rides
    go in once, as text, for the reason given below. `last_ride` is a preformatted date
    (show.py holds the timestamp).
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

    # The rides themselves, in the order and shape the spot pane lists them. A waypoint
    # whose whole description is four averages is not the spot — what people open a spot
    # for is the comments, and an importer has no second request it can make.
    #
    # Text only: mirroring the rides into <extensions> as well (which is what the
    # per-user ride export does with a ride's Nostr content) doubled the file, 35 MB →
    # 70 MB and 7 MB → 12 MB gzipped, for a channel no map app renders and that
    # dist/rides/by-spot/<id>.json already publishes as structured data.
    ride_blocks = ["\n".join(ride_lines(ride)) for ride in sort_rides(rides or [])]

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

    summary = "\n".join(line for line in lines if line)
    # Blank line between blocks: a ride's comment runs to several lines of its own, so
    # without one the list reads as a single paragraph in every importer that wraps text.
    desc = "\n\n".join([summary, *ride_blocks]) if ride_blocks else summary

    return {
        "lat": spot["lat"],
        "lon": spot["lon"],
        # The spot's real name where we have one. A list of 35k bare coordinates is
        # useless in an offline map's waypoint list, so fall back to the ride count.
        "name": detail.get("name") or f"Hitchhiking spot ({spot['review_count']} rides)",
        "desc": desc,
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
