"""Hitchhiking races: who got from city A to city B fastest.

A race is a city pair plus a timespan, defined in `RACES.md` at the repo root (see that
file for the format and the full rule set). This module parses those definitions and
ranks hitchhikers by the fastest chain of consecutive rides they logged between the two
cities. It is a pure library — `show.py` calls it and writes the result to
`dist/races.json`, which `/races` then just reads.

Not a `flask generate` script: it has no app context and no side effects of its own.
"""

import math
import re
from datetime import datetime, timedelta, timezone

# Defaults for the two tolerances, overridable per race in RACES.md.
DEFAULT_MAX_GAP_KM = 10.0  # how far apart two consecutive rides may be (drop-off -> next pickup)
DEFAULT_MAX_RADIUS_KM = 20.0  # how far a journey's start/end may be from the city centre

# A chain is one journey, not a lifetime of travel: if the next ride only departs days
# later the hitchhiker stopped over and that is a different trip, not a slow leg.
MAX_LEG_WAIT_HOURS = 48.0

# Only ~280 of 75k rides carry an arrival time, but 6.5k carry a departure time — insisting
# on both would leave every race empty. So a missing arrival is estimated from the leg's
# distance at a plausible motorway average. Estimated legs are flagged all the way to the
# UI, and the fallback only ever moves an arrival *later* than the departure, so it can
# never invent a faster-than-possible journey.
AVG_SPEED_KMH = 75.0
ROAD_FACTOR = 1.25  # straight line -> road distance, same factor helpers.haversine_np uses


def estimate_arrival(start, lat, lon, dest_lat, dest_lon):
    """Arrival time for a leg that only logged its departure."""
    km = haversine_km(lat, lon, dest_lat, dest_lon) * ROAD_FACTOR
    return start + timedelta(hours=km / AVG_SPEED_KMH)


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance in km. Straight-line on purpose — these are proximity
    tolerances ("is this the same place?"), not travelled distances, so the road-distance
    factor `helpers.haversine_np` applies would only inflate them."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$")
_KEY_RE = re.compile(r"^[-*]\s*([a-z ]+?)\s*:\s*(.+?)\s*$", re.IGNORECASE)
# "City, Country, lat, lon". The country is required: city names repeat across borders
# (Frankfurt, Cambridge, Tripoli), and a race board that just says "Frankfurt" leaves the
# reader guessing which one the coordinates mean.
_PLACE_RE = re.compile(r"^([^,]+?)\s*,\s*([^,]+?)\s*,\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")


def _parse_place(value):
    m = _PLACE_RE.match(value)
    if not m:
        return None
    city, country = m.group(1).strip(), m.group(2).strip()
    return {"name": f"{city}, {country}", "city": city, "country": country, "lat": float(m.group(3)), "lon": float(m.group(4))}


def _parse_date(value, end_of_day=False):
    try:
        d = datetime.strptime(value.strip(), "%Y-%m-%d")
    except ValueError:
        return None
    if end_of_day:
        d = d.replace(hour=23, minute=59, second=59)
    return d.replace(tzinfo=timezone.utc)


def parse_races_md(path):
    """Parse RACES.md into race dicts. Sections that don't carry a complete, well-formed
    set of keys are skipped rather than raising — the file is prose as much as config, and
    a typo in one race must not take the whole /races page down."""
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return []

    races, current, in_fence = [], None, False

    def flush(section):
        if not section:
            return
        start = _parse_place(section["keys"].get("start", ""))
        finish = _parse_place(section["keys"].get("finish", ""))
        frm = _parse_date(section["keys"].get("from", ""))
        to = _parse_date(section["keys"].get("to", ""), end_of_day=True)
        if not (start and finish and frm and to):
            return
        races.append(
            {
                "name": section["name"],
                "start": start,
                "finish": finish,
                "from": frm,
                "to": to,
                # A race can carry an event name ("Tramprennen"); most don't, and those
                # are simply virtual races between the two cities.
                "title": f"{section['keys'].get('name', UNNAMED_RACE_TITLE).strip()} {section['name']}",
                "max_gap_km": _float_or(section["keys"].get("max gap"), DEFAULT_MAX_GAP_KM),
                "max_radius_km": _float_or(section["keys"].get("max radius"), DEFAULT_MAX_RADIUS_KM),
            }
        )

    for line in lines:
        # The file documents its own format with a fenced example race — parsing that
        # would add a phantom race to the page.
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        heading = _HEADING_RE.match(line)
        if heading:
            flush(current)
            current = {"name": heading.group(1), "keys": {}}
            continue
        if current is None:
            continue
        key = _KEY_RE.match(line)
        if key:
            current["keys"][key.group(1).strip().lower()] = key.group(2)
    flush(current)
    return races


def _float_or(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _fastest_chain(rides, race):
    """Fastest journey one hitchhiker made along this race, or None.

    `rides` are that person's rides inside the timespan, sorted by departure. Works
    backwards: `best[i]` is the earliest arrival reachable by a chain that starts with
    ride i and ends near the finish city, plus the pointer to the next ride in it. Since
    a chain's duration is `last arrival - first departure`, minimising the arrival for a
    fixed first ride minimises the duration, so this one pass answers every start.
    """
    n = len(rides)
    max_wait = MAX_LEG_WAIT_HOURS * 3600
    radius = race["max_radius_km"]
    start_city, finish_city = race["start"], race["finish"]
    near_start = [haversine_km(r["lat"], r["lon"], start_city["lat"], start_city["lon"]) <= radius for r in rides]
    near_finish = [haversine_km(r["dest_lat"], r["dest_lon"], finish_city["lat"], finish_city["lon"]) <= radius for r in rides]

    best = [None] * n  # (earliest_arrival, next_index)
    for i in range(n - 1, -1, -1):
        arrival = rides[i]["end"]
        cand = (arrival, None) if near_finish[i] else None
        for j in range(i + 1, n):
            gap = (rides[j]["start"] - arrival).total_seconds()
            if gap < 0:
                continue  # the next leg cannot depart before this one arrived
            if gap > max_wait:
                break  # rides are sorted by departure, so every later j is further away
            if best[j] is None:
                continue
            if haversine_km(rides[i]["dest_lat"], rides[i]["dest_lon"], rides[j]["lat"], rides[j]["lon"]) > race["max_gap_km"]:
                continue
            if cand is None or best[j][0] < cand[0]:
                cand = (best[j][0], j)
        best[i] = cand

    winner = None
    for i in range(n):
        if not near_start[i] or best[i] is None:
            continue
        duration = (best[i][0] - rides[i]["start"]).total_seconds()
        if winner is None or duration < winner[0]:
            winner = (duration, i)
    if winner is None:
        return None

    chain, idx = [], winner[1]
    while idx is not None:
        chain.append(rides[idx])
        idx = best[idx][1]
    return {"duration_s": winner[0], "rides": chain}


def rank_race(race, rides_by_name, top=3):
    """Podium for one race: the `top` fastest hitchhikers, fastest first.

    `rides_by_name` maps hitchhiker name -> their rides (dicts with lat/lon, dest_lat/
    dest_lon and tz-aware `start`/`end` datetimes), in any order.
    """
    results = []
    for name, all_rides in rides_by_name.items():
        rides = sorted(
            (r for r in all_rides if race["from"] <= r["start"] and r["end"] <= race["to"]),
            key=lambda r: r["start"],
        )
        if not rides:
            continue
        chain = _fastest_chain(rides, race)
        if chain:
            results.append(
                {
                    "hitchhiker_name": name,
                    "duration_s": int(chain["duration_s"]),
                    "duration": format_duration(chain["duration_s"]),
                    "started": chain["rides"][0]["start"].strftime("%Y-%m-%d %H:%M"),
                    "finished": chain["rides"][-1]["end"].strftime("%Y-%m-%d %H:%M"),
                    # True when any leg's arrival had to be estimated, so the UI can say so.
                    "estimated": any(r.get("estimated") for r in chain["rides"]),
                    # Only the count: the page reports how many lifts it took, but the
                    # individual rides are the hitchhiker's own log, not race results.
                    "ride_count": len(chain["rides"]),
                }
            )
    results.sort(key=lambda e: e["duration_s"])
    return results[:top]


def format_duration(seconds):
    """e.g. "1 d 4 h 20 min" — journeys here run from a few hours to a couple of days."""
    seconds = int(seconds)
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    parts = []
    if days:
        parts.append(f"{days} d")
    if hours or days:
        parts.append(f"{hours} h")
    parts.append(f"{minutes} min")
    return " ".join(parts)


# Prefix for a race nobody organised: the page still needs to call it something, and
# "Virtual race Berlin → Prague" says exactly what it is.
UNNAMED_RACE_TITLE = "Virtual race"

# How far ahead the page looks: a race starting later than this is not news yet. One
# calendar month, not a flat 30 days — an event starting "next month" on the 22nd would
# otherwise miss the cut by a day in every 31-day month.
UPCOMING_MONTHS = 1


def _add_months(when, months):
    """`when` shifted by whole months, clamped to the target month's last day."""
    month = when.month - 1 + months
    year, month = when.year + month // 12, month % 12 + 1
    last_day = [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][
        month - 1
    ]
    return when.replace(year=year, month=month, day=min(when.day, last_day))


def current_races(races, now=None, upcoming_months=UPCOMING_MONTHS):
    """The races `/races` shows: the ones running right now plus the ones starting within
    the next month. Finished races and anything further out are dropped — the page is a
    "what can I race today" board, not an archive.

    Filtering happens at request time (not when show.py builds races.json) so a race
    starts and ends on its own date rather than whenever the last cron run happened. Takes
    and returns the JSON dicts, annotated with `status` ("running" | "upcoming") and, for
    upcoming ones, `starts_in_days`.
    """
    now = now or datetime.now(timezone.utc)
    horizon = _add_months(now, upcoming_months)
    visible = []
    for race in races:
        frm, to = _parse_date(race.get("from", "")), _parse_date(race.get("to", ""), end_of_day=True)
        if not frm or not to or to < now or frm > horizon:
            continue
        upcoming = frm > now
        visible.append(
            dict(
                race,
                status="upcoming" if upcoming else "running",
                starts_in_days=max(0, (frm - now).days + 1) if upcoming else 0,
            )
        )
    # Running races first, then the upcoming ones by how soon they start.
    visible.sort(key=lambda r: (r["status"] == "upcoming", r["starts_in_days"], r["name"]))
    return visible


def build_races(races_md_path, rides_by_name, top=3):
    """[{name, title, start, finish, from, to, entries: [...]}] for every race in RACES.md."""
    out = []
    for race in parse_races_md(races_md_path):
        out.append(
            {
                "name": race["name"],
                "title": race["title"],
                "start": race["start"]["name"],
                "finish": race["finish"]["name"],
                "from": race["from"].strftime("%Y-%m-%d"),
                "to": race["to"].strftime("%Y-%m-%d"),
                "max_gap_km": race["max_gap_km"],
                "max_radius_km": race["max_radius_km"],
                "entries": rank_race(race, rides_by_name, top=top),
            }
        )
    return out
