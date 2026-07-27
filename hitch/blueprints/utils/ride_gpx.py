"""Turn a user's RideEvent rows into a GPX document they can import anywhere.

Backs the private download page (`/me/downloads` → `/me/rides.gpx`). The shape
follows what an offline map actually does with the file:

* a ride with no recorded destination becomes a **`<wpt>`** — all we know is
  where the hitchhiker stood, and inventing an endpoint would put a line on
  their map that no car ever drove;
* a ride that recorded where it ended becomes a **`<rte>`** from pickup to
  destination, so the leg is drawn.

Either way the *whole* ride record is attached: a human-readable `<desc>` for
importers that only show text, and the complete Nostr content mirrored into
`<extensions>` (see hitch/gpx.py) so nothing the user logged is lost in the
export — including fields this app does not render yet.
"""

import json
import os

from hitch.blueprints.utils.ride_facts import spot_id_for, stop_facts
from hitch.gpx import build_route, build_waypoint, gpx_root, serialize
from hitch.helpers import get_dirs, haversine_np

SITE_URL = "https://maps.hitchwiki.org"

# Icon hint for importers that draw a symbol per waypoint. One of the Garmin symbol
# names most tools recognise; an unknown name degrades to a default pin rather than
# breaking the file, so this is safe to change.
WAYPOINT_SYM = "Flag, Blue"


def _spot_names(coords):
    """Display names for spot coordinates, from the per-spot detail files.

    Same names the map shows (hitch/scripts/spot_naming.py resolves them; show.py
    writes them into dist/rides/by-spot/<id>.json). Read from disk rather than
    re-derived because the cascade needs the OSM/service-area tables show.py
    already joined. A user has tens of rides, so this is tens of small file reads;
    a coordinate with no spot file (a destination nobody has ever been picked up
    at) simply stays unnamed.
    """
    by_spot_dir = os.path.join(get_dirs()["dist"], "rides", "by-spot")
    names = {}
    for lat, lon in coords:
        if lat is None or lon is None:
            continue
        spot_id = spot_id_for(lat, lon)
        if spot_id in names:
            continue
        names[spot_id] = None
        try:
            with open(os.path.join(by_spot_dir, f"{spot_id}.json"), encoding="utf-8") as f:
                names[spot_id] = (json.load(f).get("spot") or {}).get("name")
        except (OSError, ValueError):
            continue
    return names


def _name_for(names, lat, lon):
    if lat is None or lon is None:
        return None
    return names.get(spot_id_for(lat, lon))


def _format_minutes(minutes):
    if minutes is None:
        return None
    if minutes < 60:
        return f"{minutes} min"
    hours, rest = divmod(int(minutes), 60)
    return f"{hours} h {rest} min" if rest else f"{hours} h"


def _driver_summary(content):
    """One line describing the driver, from the occupant flagged `was_driver`."""
    driver = next((o for o in (content.get("occupants") or []) if isinstance(o, dict) and o.get("was_driver")), None)
    if not driver:
        return None
    bits = [
        driver.get("gender"),
        f"born {driver['year_of_birth']}" if driver.get("year_of_birth") else None,
        f"from {driver['origin_country']}" if driver.get("origin_country") else None,
        "speaks " + ", ".join(driver["languages"]) if driver.get("languages") else None,
        "picks up because: " + ", ".join(driver["reasons_to_pick_up"]) if driver.get("reasons_to_pick_up") else None,
    ]
    bits = [b for b in bits if b]
    return "Driver: " + "; ".join(bits) if bits else None


def _signal_methods(content):
    """Every signalling method used across the ride's signals, in first-seen order."""
    methods = []
    for signal in content.get("signals") or []:
        for method in (signal or {}).get("methods") or []:
            if method not in methods:
                methods.append(method)
    return methods


def ride_description(ride, content, facts, distance_km):
    """The human-readable `<desc>` block: every fact we hold, one per line.

    Plain "Label: value" lines rather than prose — this text is shown in a narrow
    detail pane in most importers, and is what a user greps when they open the
    file in an editor.
    """
    hitchhikers = [h.get("nickname") for h in (content.get("hitchhikers") or []) if isinstance(h, dict) and h.get("nickname")]
    signals = _signal_methods(content)
    transport = content.get("mode_of_transportation") or {}
    no_ride = content.get("no_ride")

    lines = [
        f"Rating: {ride.rating}/5" if ride.rating else None,
        f"Waited: {_format_minutes(facts['waiting_minutes'])}" if facts["waiting_minutes"] is not None else None,
        f"Departed: {facts['departure_time']}" if facts["departure_time"] else None,
        f"Arrived: {facts['arrival_time']}" if facts["arrival_time"] else None,
        f"Distance: {distance_km:.0f} km" if distance_km is not None else None,
        f"Signalled with: {', '.join(signals)}" if signals else None,
        f"Vehicle: {transport.get('kind')}" if transport.get("kind") else None,
        f"Licence plate from: {transport.get('license_plate_country')}" if transport.get("license_plate_country") else None,
        _driver_summary(content),
        "Would ride again: " + ("yes" if content.get("would_ride_again") else "no")
        if content.get("would_ride_again") is not None
        else None,
        # A give-up is a real, deliberate record ("waited here, never got picked
        # up"), not missing data — say so explicitly so it isn't read as a ride.
        "Gave up here — never got picked up" if no_ride is not None else None,
        "Gave up because: " + ", ".join(no_ride["reasons"]) if isinstance(no_ride, dict) and no_ride.get("reasons") else None,
        f"Hitchhikers: {', '.join(hitchhikers)}" if hitchhikers else None,
        f"Logged: {ride.submission_time}" if ride.submission_time else None,
        f"Source: {ride.source}" if ride.source else None,
        f"Licence: {ride.license}" if ride.license else None,
    ]
    comment = (ride.comment or "").strip()
    if comment:
        lines.append("")
        lines.append(comment)
    return "\n".join(line for line in lines if line is not None)


def _ride_title(names, facts, ride):
    """Title of the form `<start> → <destination>` where the spots are named, else a dated fallback."""
    start = _name_for(names, facts["pickup_lat"], facts["pickup_lon"])
    end = _name_for(names, facts["dest_lat"], facts["dest_lon"])
    date = (ride.submission_time or "")[:10]
    if start and end:
        title = f"{start} → {end}"
    elif start:
        title = start
    elif end:
        title = f"→ {end}"
    else:
        title = "Hitchhiking ride" if facts["dest_lat"] is not None else "Hitchhiking spot"
    return f"{title} ({date})" if date else title


def rides_gpx(rides, username):
    """Serialise RideEvent rows into a GPX document (bytes).

    `rides` are RideEvent rows; anything without a pickup coordinate is skipped,
    since GPX has nowhere to put a ride with no location.
    """
    all_facts = [(ride, ride.content or {}, stop_facts((ride.content or {}).get("stops"))) for ride in rides]
    names = _spot_names(
        [(f["pickup_lat"], f["pickup_lon"]) for _, _, f in all_facts] + [(f["dest_lat"], f["dest_lon"]) for _, _, f in all_facts]
    )

    root = gpx_root(
        name=f"Hitchhiking rides logged by {username}",
        desc=(
            f"{len(all_facts)} hitchhiking rides exported from Hitchwiki Maps. "
            "Rides with a recorded destination are routes; rides without one are waypoints. "
            "The full record of each ride is in its <extensions> element."
        ),
        author=username,
        link={"href": f"{SITE_URL}/account/{username}", "text": f"{username} on Hitchwiki Maps"},
        keywords="hitchhiking, Hitchwiki Maps",
    )

    for ride, content, facts in all_facts:
        if facts["pickup_lat"] is None or facts["pickup_lon"] is None:
            continue

        # The map's road-distance estimate (great-circle x 1.25), the same figure the
        # profile and the spot pane show — not the straight line — so a user comparing
        # the export against the site doesn't find two different numbers.
        distance_km = None
        if facts["dest_lat"] is not None and facts["dest_lon"] is not None:
            distance_km = float(haversine_np(facts["pickup_lat"], facts["pickup_lon"], facts["dest_lat"], facts["dest_lon"]))

        entry = {
            "name": _ride_title(names, facts, ride),
            "desc": ride_description(ride, content, facts, distance_km),
            "time": facts["departure_time"] or ride.submission_time,
            "src": ride.source,
            "type": "hitchhiking",
            "link": {"href": f"{SITE_URL}/ride/{ride.d}", "text": "This ride on Hitchwiki Maps"} if ride.d else None,
            "extensions": {
                # The verbatim Nostr content, so every field of the hitchhiking data
                # standard survives the export even where this app has no UI for it.
                "ride": content,
                "nostr": {"id": ride.id, "pubkey": ride.pubkey, "d": ride.d, "kind": ride.kind, "created_at": ride.created_at},
            },
        }

        if facts["dest_lat"] is None or facts["dest_lon"] is None:
            entry["sym"] = WAYPOINT_SYM
            root.append(build_waypoint(dict(entry, lat=facts["pickup_lat"], lon=facts["pickup_lon"])))
            continue

        start_name = _name_for(names, facts["pickup_lat"], facts["pickup_lon"])
        end_name = _name_for(names, facts["dest_lat"], facts["dest_lon"])
        root.append(
            build_route(
                dict(
                    entry,
                    points=[
                        {
                            "lat": facts["pickup_lat"],
                            "lon": facts["pickup_lon"],
                            "name": start_name or "Picked up",
                            "time": facts["departure_time"],
                        },
                        {
                            "lat": facts["dest_lat"],
                            "lon": facts["dest_lon"],
                            "name": end_name or "Dropped off",
                            "time": facts["arrival_time"],
                        },
                    ],
                )
            )
        )

    return serialize(root)
