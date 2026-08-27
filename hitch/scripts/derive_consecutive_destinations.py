"""Derive ride destinations from consecutively-logged rides by the same user.

Many hitchwiki.org / hitchmap.com rides reach Nostr with no destination (a single
`stops` entry — just the start). But users routinely logged a whole trip in one sitting:
a run of rides entered minutes apart whose start points march in one direction along a
road. When that happens the start of each ride is, in practice, the destination of the
one before it. This script reconstructs those chains and stores the inferred destination
in `derived_ride_location` (the same table the comment-mining pipeline writes to), tagged
`kind='derived-consecutive-ride'` so the two provenance methods stay distinguishable.

Unlike the comment-derived city centres, the coordinate stored here is an *exact logged
spot* (the next ride's start), so `is_exact=1`.

Standalone script (plain `python3`, not `flask generate`) — an occasional batch job, not a
cron task. Reads `ride_event` and writes `derived_ride_location` via plain sqlite3, so it
runs on the minimal host venv and against the root-owned prod DB via sudo:

    python3 hitch/scripts/derive_consecutive_destinations.py --db db/hitchhiking-prod.sqlite --dry-run
    sudo python3 hitch/scripts/derive_consecutive_destinations.py --db db/hitchhiking-prod.sqlite

The chain heuristic is deliberately conservative (high precision over recall):

  * only sources hitchwiki.org / hitchmap.com, only named hitchhikers (never "Anonymous")
  * only rides that have a start but no distinct destination
  * a chain is a run of the user's rides, ordered by submission_time, where each successive
    ride was logged within GAP_MAX minutes of the previous one and its start lies
    LEG_MIN_KM..LEG_MAX_KM from the previous start (a plausible single hitchhiking leg)
  * every new leg must keep roughly the same bearing as the previous one (<= BEARING_TOL),
    and the whole chain must be near-straight (net displacement / path length >= STRAIGHTNESS)
  * a chain needs >= MIN_CHAIN rides, so a direction is actually established (a bare pair
    proves nothing); the last ride of a chain gets no destination (nothing follows it)

Existing rows are never overwritten (ON CONFLICT DO NOTHING), so a higher-quality
comment-derived destination always wins over a consecutive-ride guess for the same ride.
"""

import argparse
import json
import math
import sqlite3
import sys
import time
from collections import defaultdict

if __package__:
    from hitch.scripts.map_revision import dist_dir_for_database, mark_map_data_dirty
else:
    from map_revision import dist_dir_for_database, mark_map_data_dirty
from datetime import datetime

KIND = "derived-consecutive-ride"

# Heuristic thresholds — tuned for precision. See module docstring.
GAP_MAX_MIN = 20.0  # max minutes between two consecutively-logged rides in a chain
LEG_MIN_KM = 5.0  # below this the two starts are effectively the same spot
LEG_MAX_KM = 300.0  # above this it is likely a separate trip, not the next leg
BEARING_TOL = 50.0  # degrees a leg may deviate from the previous leg's bearing
STRAIGHTNESS = 0.80  # net displacement / total path length for the whole chain
MIN_CHAIN = 3  # rides; fewer cannot establish a consistent direction


def _haversine(a_lat, a_lon, b_lat, b_lon):
    r = 6371.0
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp, dl = math.radians(b_lat - a_lat), math.radians(b_lon - a_lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def _bearing(a_lat, a_lon, b_lat, b_lon):
    la1, la2 = math.radians(a_lat), math.radians(b_lat)
    dlo = math.radians(b_lon - a_lon)
    y = math.sin(dlo) * math.cos(la2)
    x = math.cos(la1) * math.sin(la2) - math.sin(la1) * math.cos(la2) * math.cos(dlo)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def _bearing_diff(b1, b2):
    return abs((b1 - b2 + 180) % 360 - 180)


def _first_coord(stop):
    loc = (stop or {}).get("location") or {}
    lat, lon = loc.get("latitude"), loc.get("longitude")
    if lat is None or lon is None:
        return None
    try:
        return float(lat), float(lon)
    except (TypeError, ValueError):
        return None


def _start_without_dest(stops):
    """Return (lat, lon) of the start if the ride has a start but no distinct destination,
    else None (rides that already know where they went need no enrichment)."""
    if not isinstance(stops, list) or not stops:
        return None
    start = _first_coord(stops[0])
    if not start:
        return None
    for s in stops[1:]:
        c = _first_coord(s)
        if c and (abs(c[0] - start[0]) > 1e-6 or abs(c[1] - start[1]) > 1e-6):
            return None
    return start


def _nickname(hitchhikers_json):
    try:
        hh = json.loads(hitchhikers_json) if isinstance(hitchhikers_json, str) else hitchhikers_json
        nick = (hh or [{}])[0].get("nickname")
    except (ValueError, TypeError, AttributeError, IndexError):
        return None
    if not nick or nick.strip().lower() == "anonymous":
        return None
    return nick


def load_rides(conn):
    """Named, no-destination rides from hitchwiki/hitchmap, grouped by nickname and sorted
    by submission time. Each entry: (dt, lat, lon, d, source)."""
    by_user = defaultdict(list)
    q = "SELECT d, stops, hitchhikers, submission_time, source FROM ride_event WHERE source IN ('hitchwiki.org', 'hitchmap.com')"
    for d, stops_json, hh_json, sub, source in conn.execute(q):
        if not d or not sub:
            continue
        nick = _nickname(hh_json)
        if not nick:
            continue
        try:
            stops = json.loads(stops_json) if stops_json else None
        except ValueError:
            continue
        start = _start_without_dest(stops)
        if not start:
            continue
        try:
            dt = datetime.fromisoformat(sub.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            continue
        by_user[nick].append((dt, start[0], start[1], d, source))
    for rides in by_user.values():
        rides.sort(key=lambda r: r[0])
    return by_user


def find_chains(rides):
    """Split one user's time-sorted rides into directional chains (list of ride tuples)."""
    chains = []
    n = len(rides)
    i = 0
    while i < n - 1:
        chain = [rides[i]]
        j = i + 1
        while j < n:
            prev, cur = chain[-1], rides[j]
            gap_min = (cur[0] - prev[0]).total_seconds() / 60.0
            dist = _haversine(prev[1], prev[2], cur[1], cur[2])
            ok_dir = True
            # Once we have a leg to compare against, the next leg must keep the bearing.
            if len(chain) >= 2:
                b_prev = _bearing(chain[-2][1], chain[-2][2], chain[-1][1], chain[-1][2])
                b_cur = _bearing(chain[-1][1], chain[-1][2], cur[1], cur[2])
                ok_dir = _bearing_diff(b_prev, b_cur) <= BEARING_TOL
            if 0 <= gap_min <= GAP_MAX_MIN and LEG_MIN_KM <= dist <= LEG_MAX_KM and ok_dir:
                chain.append(cur)
                j += 1
            else:
                break
        if len(chain) >= MIN_CHAIN:
            total = sum(_haversine(chain[k][1], chain[k][2], chain[k + 1][1], chain[k + 1][2]) for k in range(len(chain) - 1))
            net = _haversine(chain[0][1], chain[0][2], chain[-1][1], chain[-1][2])
            if total and net / total >= STRAIGHTNESS:
                chains.append(chain)
            # Restart from whatever ride broke (or ended) the chain.
            i = j
        else:
            i += 1
    return chains


def build_rows(by_user):
    """One derived-destination row per non-terminal ride in every accepted chain.
    Row shape matches derived_ride_location's INSERT column order."""
    now = int(time.time())
    rows = []
    for nick, rides in by_user.items():
        for chain in find_chains(rides):
            # Each ride's destination is the next ride's (logged, exact) start.
            for k in range(len(chain) - 1):
                d = chain[k][3]
                nxt = chain[k + 1]
                note = f"next ride by {nick} started here {(nxt[0] - chain[k][0]).total_seconds() / 60.0:.0f} min later"
                rows.append((d, nxt[1], nxt[2], 1, None, note, KIND, now))
    return rows


def _ensure_table(conn):
    # CREATE IF NOT EXISTS mirrors DerivedRideLocation; there is no migration framework.
    conn.execute(
        """CREATE TABLE IF NOT EXISTS derived_ride_location (
             d TEXT PRIMARY KEY,
             latitude REAL NOT NULL,
             longitude REAL NOT NULL,
             is_exact BOOLEAN NOT NULL DEFAULT 0,
             location_name TEXT,
             source_comment TEXT,
             kind TEXT,
             created_at INTEGER
           )"""
    )


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", required=True, help="path to the sqlite database")
    ap.add_argument("--dry-run", action="store_true", help="report what would be written, change nothing")
    ap.add_argument("--limit", type=int, default=15, help="how many example chains to print")
    args = ap.parse_args(argv)

    conn = sqlite3.connect(args.db)
    by_user = load_rides(conn)
    rows = build_rows(by_user)

    n_chains = sum(len(find_chains(r)) for r in by_user.values())
    n_users = sum(1 for r in by_user.values() if find_chains(r))
    print(f"{len(rows)} derived destinations across {n_chains} chains from {n_users} users")

    # Preview a few chains so the heuristic is auditable before committing.
    shown = 0
    for nick, rides in by_user.items():
        for chain in find_chains(rides):
            if shown >= args.limit:
                break
            legs = " -> ".join(f"{c[1]:.4f},{c[2]:.4f}" for c in chain)
            print(f"  [{chain[0][0].date()}] {nick} ({len(chain)}): {legs}")
            shown += 1
        if shown >= args.limit:
            break

    if args.dry_run:
        print("dry-run: nothing written")
        return 0

    _ensure_table(conn)
    # DO NOTHING (not DO UPDATE): never clobber an existing derived destination — a
    # comment-derived city or an earlier run's row outranks a fresh consecutive-ride guess.
    before = conn.execute("SELECT COUNT(*) FROM derived_ride_location").fetchone()[0]
    conn.executemany(
        """INSERT INTO derived_ride_location
             (d, latitude, longitude, is_exact, location_name, source_comment, kind, created_at)
           VALUES (?,?,?,?,?,?,?,?)
           ON CONFLICT(d) DO NOTHING""",
        rows,
    )
    conn.commit()
    after = conn.execute("SELECT COUNT(*) FROM derived_ride_location").fetchone()[0]
    conn.close()
    if after != before:
        mark_map_data_dirty(dist_dir_for_database(args.db))
    print(
        f"inserted {after - before} new rows ({len(rows) - (after - before)} skipped as already present); table now has {after}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
