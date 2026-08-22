"""Scalar per-ride facts read out of a RideEvent's `stops` / `hitchhikers`.

One implementation shared by /ride/<d_tag> (which renders a single ride) and
/pending_rides.json (which serves the handful of rides show.py has not picked up yet).
show.py computes the same values in pandas across the whole table; these must stay
numerically identical to it, otherwise a ride would visibly change the moment the cron
takes over from the live endpoint.
"""

import math
import re

from hitch.helpers import haversine_np
from hitch.usernames import canonical_username

# Only the PT<n>M form our own submit path writes. Anything else (a foreign source
# using hours, a malformed value) reads as "no recorded wait" rather than a wrong
# number — an invented wait time would pollute the spot's averages.
_WAITING_DURATION_RE = re.compile(r"^PT(\d+)M$")

EARTH_RADIUS_KM = 6371


def _waypoint_from_stop(stop):
    """A displayable {lat, lon, label, arrival_time, departure_time} from one stop dict.

    `lat`/`lon` are `None` for a label-only stop (a detour named but never pinned --
    the ride form lets a hitchhiker add one without a coordinate picker). Returns None
    only when the stop has neither a coordinate nor a label -- nothing usable at all.
    """
    if not isinstance(stop, dict):
        return None
    location = stop.get("location") or {}
    lat, lon = location.get("latitude"), location.get("longitude")
    label = stop.get("label")
    # Blank/whitespace-only reads as "not labelled", matching hitchhiker_name's own
    # "don't trust a blank string as real data" convention elsewhere in this module.
    label = label.strip() if isinstance(label, str) and label.strip() else None
    if lat is None or lon is None:
        if label is None:
            return None
        lat = lon = None
    return {
        "lat": lat,
        "lon": lon,
        "label": label,
        "arrival_time": stop.get("arrival_time"),
        "departure_time": stop.get("departure_time"),
    }


def stop_facts(stops):
    """Pickup/destination coordinates and times from a ride's stop list.

    Every key is always present, `None` when the ride does not have it, so callers
    never have to distinguish "absent" from "malformed". `intermediate_stops` is the
    exception -- always a list, empty when there are none -- since callers loop over it
    directly (`{% for stop in ride.intermediate_stops %}`) rather than testing it first.
    """
    facts = {
        "pickup_lat": None,
        "pickup_lon": None,
        "dest_lat": None,
        "dest_lon": None,
        "departure_time": None,
        "arrival_time": None,
        "waiting_minutes": None,
        "intermediate_stops": [],
    }
    if not isinstance(stops, list) or not stops:
        return facts

    first = stops[0] if isinstance(stops[0], dict) else {}
    location = first.get("location") or {}
    facts["pickup_lat"] = location.get("latitude")
    facts["pickup_lon"] = location.get("longitude")
    facts["departure_time"] = first.get("departure_time")
    match = _WAITING_DURATION_RE.match(first.get("waiting_duration") or "")
    if match:
        facts["waiting_minutes"] = int(match.group(1))

    # A single-stop ride is one where the hitchhiker never recorded where they got to.
    if len(stops) > 1 and isinstance(stops[-1], dict):
        last = stops[-1]
        last_location = last.get("location") or {}
        facts["dest_lat"] = last_location.get("latitude")
        facts["dest_lon"] = last_location.get("longitude")
        facts["arrival_time"] = last.get("arrival_time")

    # Everything strictly between the first and last entry -- undefined for a ride with
    # 2 or fewer stops, where stops[1:-1] is already empty, so no separate length guard.
    facts["intermediate_stops"] = [waypoint for stop in stops[1:-1] if (waypoint := _waypoint_from_stop(stop)) is not None]

    return facts


def haversine_km(lat1, lon1, lat2, lon2):
    """Straight-line great-circle distance in km, or None when either end is missing.

    This is what /ride/<d_tag> has always shown and must keep showing. It is
    deliberately NOT the map's distance: show.py's per-ride `distance` column comes from
    `haversine_np` (hitch/helpers.py), which inflates the great-circle figure by a 1.25
    road-distance factor. `ride_map_entry` below calls `haversine_np` directly for that
    reason — reimplementing the factor here would let the two formulas drift apart.
    """
    if None in (lat1, lon1, lat2, lon2):
        return None
    rlat1, rlon1, rlat2, rlon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = rlat2 - rlat1
    dlon = rlon2 - rlon1
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def hitchhiker_name(hitchhikers):
    """Display name for a ride: the first hitchhiker's nickname, else "Anonymous".

    Mirrors get_hitchhiker_name in show.py — the literal string "Anonymous" is what the
    frontend tests against to decide whether to link to a profile — including its
    canonicalisation onto the registered account's own spelling, so a ride the map is
    showing live from the DB doesn't name its author differently from the same ride once
    show.py has written it into the generated files.
    """
    if isinstance(hitchhikers, list) and hitchhikers:
        first = hitchhikers[0]
        if isinstance(first, dict):
            nickname = first.get("nickname")
            if isinstance(nickname, str) and nickname.strip():
                return canonical_username(nickname)
    return "Anonymous"


def is_informative(name, comment, wait):
    """Whether a ride carries anything beyond a bare rating.

    show.py drops anonymous rides with no comment and no waiting time from every detail
    view (`is_informative`), so serving one here would show a ride for ten minutes and
    then silently take it away again.
    """
    return not (name == "Anonymous" and not (comment or "").strip() and wait is None)


def spot_id_for(lat, lon):
    """The spot id a coordinate belongs to.

    Must stay identical to generate_spot_id in hitch/scripts/show.py — it is the
    rides/by-spot/<id>.json filename and the id map.js derives from marker coordinates,
    so any divergence turns into a 404 or an orphaned marker.
    """
    return f"{round(float(lat), 5):.5f}_{round(float(lon), 5):.5f}"


def vehicle_kind(mode_of_transportation):
    """The vehicle a ride was taken in, or None. Twin of show.py's get_vehicle_kind."""
    if isinstance(mode_of_transportation, dict):
        return mode_of_transportation.get("kind") or None
    return None


def signal_methods(signals):
    """Unique signal methods used on a ride (["thumb", "sign"]), or None.

    Twin of show.py's get_signal_methods — order of first appearance, deduplicated.
    """
    if not isinstance(signals, list):
        return None
    seen = []
    for approach in signals:
        if not isinstance(approach, dict):
            continue
        for method in approach.get("methods") or []:
            if method and method not in seen:
                seen.append(method)
    return seen or None


def ride_map_entry(ride, images=None):
    """One /pending_rides.json entry, or None when the ride does not belong on the map.

    `ride` is any object with the RideEvent columns (`d`, `stops`, `hitchhikers`,
    `comment`, `rating`, `submission_time`, `mode_of_transportation`, `signals`,
    `no_ride`). The
    keys match what show.py writes into rides/by-spot/<id>.json plus the marker fields
    from spots.json, so map.js can feed the entry straight into the paths that already
    render both. Attributes are read directly rather than through getattr defaults: a
    caller whose shape drifts should fail here, not quietly report every ride as having
    recorded no vehicle.

    `images` is the ride's photo URLs, passed in rather than looked up here so the
    caller can batch one query for the whole pending set.
    """
    facts = stop_facts(ride.stops)
    if facts["pickup_lat"] is None or facts["pickup_lon"] is None:
        return None

    name = hitchhiker_name(ride.hitchhikers)
    if not is_informative(name, ride.comment, facts["waiting_minutes"]):
        return None

    # show.py's map distance is haversine_np's road-distance estimate (great-circle x
    # 1.25), not the ride page's straight-line haversine_km — using the same function
    # here is what keeps a pending ride's distance from jumping the moment show.py
    # regenerates and takes over.
    # A give-up carries no distance and no destination line: its last stop is where the
    # hitchhiker meant to go, not where a car took them. show.py drops both for the same
    # reason, and this entry only exists until show.py catches up -- disagreeing would
    # make a marker's line and distance vanish ten minutes after it appeared.
    dest_lat, dest_lon = facts["dest_lat"], facts["dest_lon"]
    if ride.no_ride:
        dest_lat = dest_lon = None
    distance = None
    if None not in (dest_lat, dest_lon):
        distance = float(haversine_np(facts["pickup_lat"], facts["pickup_lon"], dest_lat, dest_lon))
    vehicle = vehicle_kind(ride.mode_of_transportation)
    methods = signal_methods(ride.signals)
    return {
        # The d tag, not the Nostr event id: show.py uses the d tag as a ride's `id` in
        # the per-spot files, and the spot pane links to /ride/<id>.
        "id": ride.d,
        "spot_id": spot_id_for(facts["pickup_lat"], facts["pickup_lon"]),
        "lat": facts["pickup_lat"],
        "lon": facts["pickup_lon"],
        "dest_lat": dest_lat,
        "dest_lon": dest_lon,
        "rating": ride.rating,
        "wait": facts["waiting_minutes"],
        "distance": round(distance, 1) if distance is not None else None,
        "comment": ride.comment,
        "hitchhiker_name": name,
        "submission_time": ride.submission_time,
        "ride_datetime": facts["departure_time"],
        "arrival_datetime": facts["arrival_time"],
        # Omitted when there are none, matching the per-spot files show.py writes.
        **({"images": list(images)} if images else {}),
        # Same two filter facts, omitted the same way, so the spot pane can decide
        # about a pending ride with exactly the rules it applies to a generated one.
        **({"vehicle_kind": vehicle} if vehicle else {}),
        **({"signal_methods": methods} if methods else {}),
    }
