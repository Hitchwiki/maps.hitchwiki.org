"""Spots with a repeatable weekday pattern: same spot, same weekday, same faraway
destination, and nobody waited long. Feeds /why-not-hitchhike.

The claim the page makes is narrow and deliberately hard to earn. A spot qualifies when,
for one weekday, at least MIN_RIDES rides from it reached destinations lying within
DEST_RADIUS_KM of each other, that cluster sits at least MIN_DISTANCE_KM from the spot,
and *every* ride in it got picked up in under MAX_WAIT_MIN minutes. One slow ride
disqualifies the whole cluster — the point is "you can count on this", not "it usually
works", so a single counter-example has to be able to break it.

Reads dist/rides_index.json rather than re-deriving spots, so a row's spot_id is the same
identity /spot/<id> and the per-spot files use (show.py merges coordinates within 5 m, and
again within an OSM service-area polygon; re-clustering here would silently disagree).
That makes this script a strict downstream of `show` — run it after.

    flask --app hitch generate why_not_hitchhike

Two data rules that decide whether the output means anything:

  * **Weekday comes only from a ride's own departure_time.** The site's ride *filter* keys
    on `rd ?? t` (ride datetime, else submission time) so the filter always agrees with the
    date printed on the card. That fallback is wrong here: this page asserts something
    about the day people *rode*, and a submission timestamp is the day someone typed the
    ride in — often weeks later. Rides without a departure_time are simply not counted,
    which costs ~87% of the corpus and is the right trade for a weekday claim.
  * **Duplicate submissions are collapsed.** The same ride reaching Nostr four times is not
    four rides. Before this rule the only cluster in the entire dataset that met every
    criterion was one hitchhiker's ride submitted four times within 19 seconds.

Destination coordinates and waiting times are enriched exactly the way show.py enriches
them (derived_ride_location / derived_ride_wait), so a ride counts here whenever it counts
on the map.
"""

import json
import logging
import math
import os
from collections import Counter, defaultdict
from datetime import date, datetime, timezone

from hitch.helpers import get_db, get_dirs, write_json_file

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
logger = logging.getLogger(__name__)

# The four criteria. Changing any of these changes what the page claims, so they are
# published in the JSON and rendered on the page rather than left implicit in the code.
MIN_RIDES = 4  # rides in one destination cluster on one weekday
DEST_RADIUS_KM = 25.0  # how far apart two destinations may be and still count as "the same place"
MIN_DISTANCE_KM = 100.0  # how far the cluster must be from the spot for the ride to be worth planning around
MAX_WAIT_MIN = 30.0  # every ride in the cluster must have been picked up faster than this

# A near miss is shown separately, never mixed in with the confirmed rows. Both tiers
# require at least this many distinct dates: three rides on one afternoon say nothing
# about a weekday, and the whole premise here is repetition.
NEAR_MIN_RIDES = 2
NEAR_MIN_DATES = 2


def haversine(a_lat, a_lon, b_lat, b_lon):
    r = 6371.0
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp, dl = math.radians(b_lat - a_lat), math.radians(b_lon - a_lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def _table(conn, query):
    """Run a query, tolerating a table that an older DB doesn't have yet (the enrichment
    tables are created by their own scripts, which a fresh checkout may never have run)."""
    try:
        return conn.execute(query).fetchall()
    except Exception as exc:  # sqlite3.OperationalError: no such table
        logger.warning("skipping optional table: %s", exc)
        return []


def load_rides():
    """Every ride that can be judged at all: a canonical spot, a wait, a departure weekday
    and a destination. Returns (rides, stats)."""
    conn = get_db()

    # Enrichment, mirroring show.py: a destination mined from the comment text counts like a
    # logged one, and a wait mined from prose fills a gap but never overrides a logged wait.
    derived_dest = {}
    for d, lat, lon in _table(conn, "select d, latitude, longitude from derived_ride_location"):
        derived_dest.setdefault(d, (lat, lon))
    derived_wait = {d: float(m) for d, m in _table(conn, "select d, waiting_minutes from derived_ride_wait")}

    # Reverse-geocoded endpoints, so the page can name a spot and a destination without
    # geocoding anything at request time (ride_places.py fills this nightly).
    places = {row[0]: row[1:] for row in _table(conn, "select d_tag, from_place, from_cc, to_place, to_cc from ride_place")}
    spot_names = {sid: name for sid, name in _table(conn, "select spot_id, name from spot_name")}

    departure, destination, nickname = {}, {}, {}
    for d, stops_json, hitchhikers in _table(conn, "select d, stops, hitchhikers from ride_event where stops is not null"):
        if not d:
            continue
        try:
            stops = json.loads(stops_json)
        except (ValueError, TypeError):
            continue
        if not isinstance(stops, list) or not stops or not isinstance(stops[0], dict):
            continue

        if stops[0].get("departure_time"):
            departure[d] = stops[0]["departure_time"]
        try:
            nickname[d] = (json.loads(hitchhikers) or [{}])[0].get("nickname")
        except (ValueError, TypeError, AttributeError, IndexError):
            nickname[d] = None

        # The destination is the last stop that is actually somewhere else — a ride whose
        # only other stop repeats its start never reached a destination.
        start = stops[0].get("location") or {}
        slat, slon = start.get("latitude"), start.get("longitude")
        last = None
        for stop in stops[1:]:
            loc = (stop or {}).get("location") or {}
            if loc.get("latitude") is None or loc.get("longitude") is None:
                continue
            if slat is None or abs(loc["latitude"] - slat) > 1e-6 or abs(loc["longitude"] - slon) > 1e-6:
                last = (loc["latitude"], loc["longitude"])
        if last:
            destination[d] = last
        elif d in derived_dest:
            destination[d] = derived_dest[d]

    index_path = os.path.join(get_dirs()["dist"], "rides_index.json")
    with open(index_path, encoding="utf-8") as f:
        index = json.load(f)

    rides = []
    for entry in index:
        d = entry["id"]
        wait = entry.get("w")
        if wait is None:
            wait = derived_wait.get(d)
        stamp, dest = departure.get(d), destination.get(d)
        if wait is None or not stamp or not dest:
            continue
        # Only the leading YYYY-MM-DD is read: the stamp is already the ride's own local
        # wall-clock time, and re-interpreting the offset would move a ride logged near
        # midnight onto the wrong day — the exact thing this page must not get wrong.
        try:
            day = date.fromisoformat(stamp[:10])
        except ValueError:
            continue
        from_place, from_cc, to_place, to_cc = places.get(d, (None, None, None, None))
        rides.append(
            {
                "d": d,
                "spot_id": entry["sid"],
                "lat": entry["lat"],
                "lon": entry["lon"],
                "spot_name": spot_names.get(entry["sid"]) or from_place,
                "weekday": day.weekday(),
                "date": stamp[:10],
                "stamp": stamp,
                "wait": float(wait),
                "dest_lat": dest[0],
                "dest_lon": dest[1],
                "dest_name": to_place,
                "dest_cc": to_cc,
                "nick": nickname.get(d),
            }
        )

    # Collapse duplicate submissions of one ride: same spot, same hitchhiker, same departure
    # instant, same destination, same wait. See the module docstring for why this matters.
    seen, deduped = set(), []
    for ride in rides:
        key = (
            ride["spot_id"],
            (ride["nick"] or "").strip().lower(),
            ride["stamp"],
            round(ride["dest_lat"], 4),
            round(ride["dest_lon"], 4),
            ride["wait"],
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(ride)

    stats = {"rides_indexed": len(index), "rides_usable": len(deduped), "duplicates_collapsed": len(rides) - len(deduped)}
    logger.info("usable rides: %(rides_usable)s of %(rides_indexed)s (%(duplicates_collapsed)s duplicates collapsed)", stats)
    return deduped, stats


def cluster_destinations(rides):
    """Greedily group rides whose destinations lie within DEST_RADIUS_KM of each other.

    Seeds are taken most-crowded-first so the biggest genuine cluster forms before a
    straggler can claim its members; ties break on ride id to keep runs reproducible.
    """

    def near(a, b):
        return haversine(a["dest_lat"], a["dest_lon"], b["dest_lat"], b["dest_lon"]) <= DEST_RADIUS_KM

    remaining = list(rides)
    clusters = []
    while len(remaining) >= NEAR_MIN_RIDES:
        neighbours = [(sum(1 for o in remaining if near(r, o)), r["d"], r) for r in remaining]
        _, _, seed = max(neighbours, key=lambda n: (n[0], n[1]))
        members = [r for r in remaining if near(seed, r)]
        if len(members) < NEAR_MIN_RIDES:
            break
        clusters.append(members)
        chosen = {r["d"] for r in members}
        remaining = [r for r in remaining if r["d"] not in chosen]
    return clusters


def summarise(spot_id, weekday, members):
    """Turn one destination cluster into the row the page renders."""
    lat, lon = members[0]["lat"], members[0]["lon"]
    distances = [haversine(lat, lon, r["dest_lat"], r["dest_lon"]) for r in members]
    waits = [r["wait"] for r in members]
    dates = sorted({r["date"] for r in members})
    names = Counter(r["dest_name"] for r in members if r["dest_name"])
    spot_names = Counter(r["spot_name"] for r in members if r["spot_name"])
    countries = Counter(r["dest_cc"] for r in members if r["dest_cc"])

    return {
        "spot_id": spot_id,
        "spot_name": spot_names.most_common(1)[0][0] if spot_names else None,
        "lat": lat,
        "lon": lon,
        # Stored as an index, never a name: show.py's cards are written once and rendered in
        # 31 languages, so a baked-in weekday would be wrong in 30 of them.
        "weekday": weekday,
        "n_rides": len(members),
        "n_dates": len(dates),
        "dates": dates,
        "dest_name": names.most_common(1)[0][0] if names else None,
        "dest_cc": countries.most_common(1)[0][0] if countries else None,
        "dest_lat": sum(r["dest_lat"] for r in members) / len(members),
        "dest_lon": sum(r["dest_lon"] for r in members) / len(members),
        "avg_km": round(sum(distances) / len(distances)),
        "min_km": round(min(distances)),
        "max_km": round(max(distances)),
        "avg_wait": round(sum(waits) / len(waits)),
        "max_wait": round(max(waits)),
        "rides": [
            {"d": r["d"], "date": r["date"], "wait": round(r["wait"]), "km": round(km), "to": r["dest_name"]}
            for r, km in sorted(zip(members, distances), key=lambda pair: pair[0]["date"])
        ],
    }


def build():
    rides, stats = load_rides()

    by_spot_weekday = defaultdict(list)
    for ride in rides:
        by_spot_weekday[(ride["spot_id"], ride["weekday"])].append(ride)

    matches, near_misses = [], []
    for (spot_id, weekday), group in by_spot_weekday.items():
        if len(group) < NEAR_MIN_RIDES:
            continue
        lat, lon = group[0]["lat"], group[0]["lon"]
        # A destination has to be worth planning a day around; anything closer is a lift,
        # not a route. Filtering before clustering keeps a nearby suburb from anchoring one.
        far = [r for r in group if haversine(lat, lon, r["dest_lat"], r["dest_lon"]) >= MIN_DISTANCE_KM]
        if len(far) < NEAR_MIN_RIDES:
            continue

        for members in cluster_destinations(far):
            slow = [r for r in members if r["wait"] >= MAX_WAIT_MIN]
            row = summarise(spot_id, weekday, members)

            if len(members) >= MIN_RIDES and not slow:
                matches.append(row)
            elif row["n_dates"] < NEAR_MIN_DATES:
                continue  # one afternoon is not a weekday pattern
            elif not slow and len(members) < MIN_RIDES:
                row["miss"] = "few-rides"
                near_misses.append(row)
            elif len(slow) == 1 and len(members) >= MIN_RIDES:
                row["miss"] = "one-slow-ride"
                row["slow_wait"] = round(slow[0]["wait"])
                near_misses.append(row)

    # Most-evidenced first: more rides, then more distinct dates, then the shortest waits.
    matches.sort(key=lambda r: (-r["n_rides"], -r["n_dates"], r["avg_wait"]))
    near_misses.sort(key=lambda r: (-r["n_rides"], -r["n_dates"], r["avg_wait"]))

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "criteria": {
            "min_rides": MIN_RIDES,
            "dest_radius_km": DEST_RADIUS_KM,
            "min_distance_km": MIN_DISTANCE_KM,
            "max_wait_min": MAX_WAIT_MIN,
        },
        "coverage": stats,
        "matches": matches,
        "near_misses": near_misses,
    }


result = build()
logger.info("matches: %d, near misses: %d", len(result["matches"]), len(result["near_misses"]))
write_json_file(result, "why_not_hitchhike.json")
