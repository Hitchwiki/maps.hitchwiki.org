"""Count the reasons drivers gave for stopping, as logged by the hitchhikers they picked up.

Only rides whose driver occupant carries at least one ``reasons_to_pick_up`` answer are
counted. A ride that names several reasons counts once under each, so shares are the share
of answering rides that mention a reason and do not sum to 100%.
"""

import json
import re
import statistics
from collections import Counter

from hitch.blueprints.utils.safety_statistics import _driver


def summarise_rows(rows):
    """``rows`` are ``(occupants, no_ride[, ride])`` tuples straight from ``ride_event``.

    ``ride`` (optional) carries the driver's trip purposes in ``reasons``; they are counted over
    the same answering rides as the stop reasons.
    """
    counts = Counter()
    purposes = Counter()
    answered = 0
    total = 0
    for row in rows:
        occupants, no_ride = row[0], row[1]
        ride = row[2] if len(row) > 2 else None
        total += 1
        if no_ride:
            continue
        reasons = (_driver(occupants) or {}).get("reasons_to_pick_up") or []
        if isinstance(reasons, str):
            reasons = [reasons]
        reasons = {r for r in reasons if isinstance(r, str)}
        if not reasons:
            continue
        answered += 1
        counts.update(reasons)
        if isinstance(ride, str):
            try:
                ride = json.loads(ride)
            except ValueError:
                ride = None
        trip = ride.get("reasons") if isinstance(ride, dict) else None
        if isinstance(trip, list):
            purposes.update({r for r in trip if isinstance(r, str)})
    ranked = [{"reason": code, "rides": n} for code, n in counts.most_common()]
    trips = [{"reason": code, "rides": n} for code, n in purposes.most_common()]
    return {"reasons": ranked, "trip_purposes": trips, "coverage": {"rides_total": total, "rides_answered": answered}}


_ISO_WAIT = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?$")
MIN_SEASON_RIDES = 300
# Northern-hemisphere only: the season of a month is hemisphere-specific.
REGION_BOXES = {
    "Europe": (35, 60, -10, 30),
    "North America": (15, 72, -170, -50),
}
SEASON_BY_MONTH = {
    12: "winter", 1: "winter", 2: "winter", 3: "spring", 4: "spring", 5: "spring",
    6: "summer", 7: "summer", 8: "summer", 9: "autumn", 10: "autumn", 11: "autumn",
}  # fmt: skip


def _first_stop_wait(stops):
    """``(region, season, minutes)`` for a ride's first stop, or None when unreadable."""
    if isinstance(stops, str):
        try:
            stops = json.loads(stops)
        except ValueError:
            return None
    if not isinstance(stops, list) or not stops or not isinstance(stops[0], dict):
        return None
    stop = stops[0]
    match = _ISO_WAIT.match(stop.get("waiting_duration") or "")
    when = stop.get("departure_time")
    loc = stop.get("location") or {}
    if not match or not isinstance(when, str) or match.group(0) == "PT":
        return None
    try:
        month = int(when[5:7])
        lat, lon = float(loc["latitude"]), float(loc["longitude"])
    except (KeyError, TypeError, ValueError):
        return None
    minutes = int(match.group(1) or 0) * 60 + int(match.group(2) or 0)
    if minutes > 600 or month not in SEASON_BY_MONTH:
        return None
    for region, (lat0, lat1, lon0, lon1) in REGION_BOXES.items():
        if lat0 <= lat <= lat1 and lon0 <= lon <= lon1:
            return region, SEASON_BY_MONTH[month], minutes
    return None


def summarise_season_waits(stops_rows):
    """Median first-stop wait per region and season; regions below the sample floor are dropped."""
    buckets = {}
    for stops in stops_rows:
        parsed = _first_stop_wait(stops)
        if parsed:
            buckets.setdefault(parsed[0], {}).setdefault(parsed[1], []).append(parsed[2])
    out = []
    for region, seasons in buckets.items():
        if any(len(seasons.get(name, ())) < MIN_SEASON_RIDES for name in ("winter", "summer")):
            continue
        rows = [
            {"season": name, "rides": len(waits), "median": statistics.median(waits)}
            for name in ("winter", "spring", "summer", "autumn")
            if len(waits := seasons.get(name, ())) >= MIN_SEASON_RIDES
        ]
        out.append({"region": region, "seasons": rows})
    return out
