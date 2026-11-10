"""Aggregate the route-request log into publishable corridors.

`logs/route_requests.csv` holds one row per planner search (see route_request_log.py).
The raw log must never be public, so this keeps only corridors (start cell -> destination
cell on a coarse grid) that at least `MIN_REQUESTS` requests and `MIN_DAYS` distinct days
support. No timestamps, names or exact coordinates leave this function.
"""

import csv
from collections import defaultdict

CELL_DEG = 0.5
MIN_REQUESTS = 5
MIN_DAYS = 3


def _cell(lat, lon):
    return (round(lat // CELL_DEG * CELL_DEG, 2), round(lon // CELL_DEG * CELL_DEG, 2))


def summarise_route_demand(rows):
    """rows: iterable of dicts with the route_requests.csv columns."""
    total = 0
    bad = 0
    corridors = defaultdict(lambda: {"requests": 0, "days": set()})
    for row in rows:
        try:
            a = _cell(float(row["start_lat"]), float(row["start_lon"]))
            b = _cell(float(row["dest_lat"]), float(row["dest_lon"]))
            day = (row.get("timestamp") or "")[:10]
        except (KeyError, TypeError, ValueError):
            bad += 1
            continue
        total += 1
        if a == b or not day:
            continue
        entry = corridors[(a, b)]
        entry["requests"] += 1
        entry["days"].add(day)
    kept = [
        {"from": list(a), "to": list(b), "requests": v["requests"], "days": len(v["days"])}
        for (a, b), v in corridors.items()
        if v["requests"] >= MIN_REQUESTS and len(v["days"]) >= MIN_DAYS
    ]
    kept.sort(key=lambda c: (-c["requests"], c["from"], c["to"]))
    return {
        "cell_deg": CELL_DEG,
        "min_requests": MIN_REQUESTS,
        "min_days": MIN_DAYS,
        "total_requests": total,
        "unparsable_rows": bad,
        "corridors": kept[:200],
    }


def summarise_route_feedback(rows):
    """Votes on live route results (route_feedback.csv). Counts only: free text is never published."""
    up = down = texts = bad = excluded_auto = 0
    corridors = defaultdict(lambda: {"up": 0, "down": 0})
    for row in rows:
        # #1370: `auto` is a trailing column; files written before it have a 7-column header,
        # so DictReader parks the extra value under the None key.
        flag = (row.get("auto") or (row.get(None) or [""])[0] or "").strip()
        if flag == "1":
            excluded_auto += 1
            continue
        vote = (row.get("vote") or "").strip().lower()
        if vote not in ("up", "down"):
            bad += 1
            continue
        if vote == "up":
            up += 1
        else:
            down += 1
        if (row.get("text") or "").strip():
            texts += 1
        try:
            a = _cell(float(row["start_lat"]), float(row["start_lon"]))
            b = _cell(float(row["dest_lat"]), float(row["dest_lon"]))
        except (KeyError, TypeError, ValueError):
            continue
        corridors[(a, b)][vote] += 1
    rows_out = [{"from": list(a), "to": list(b), **v} for (a, b), v in corridors.items()]
    rows_out.sort(key=lambda c: (-(c["up"] + c["down"]), c["from"], c["to"]))
    return {"votes_up": up, "votes_down": down, "with_text": texts, "unparsable_rows": bad, "excluded_auto": excluded_auto, "corridors": rows_out[:100]}


def read_route_requests(path):
    try:
        with open(path, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except FileNotFoundError:
        return []


# Free-text filters are user input and are never reported; only the on/off style filters are.
FILTER_FIELDS_PUBLIC = [
    "recent",
    "osmonly",
    "carpoolingonly",
    "fuelonly",
    "hitchwikionly",
    "mindistance",
    "minrides",
    "minrating",
    "vehicle",
    "method",
    "mindate",
    "maxdate",
    "weekday",
]


def summarise_filter_demand(rows):
    """How often each filter was part of a settled filter set, and how often that set matched 0 spots."""
    used = {f: 0 for f in FILTER_FIELDS_PUBLIC}
    zero = {f: 0 for f in FILTER_FIELDS_PUBLIC}
    total = 0
    for row in rows:
        total += 1
        try:
            empty = int(row.get("matches", "")) == 0
        except (TypeError, ValueError):
            empty = False
        for f in FILTER_FIELDS_PUBLIC:
            if (row.get(f) or "").strip() not in ("", "0", "false", "False"):
                used[f] += 1
                zero[f] += empty
    return {
        "total_filter_requests": total,
        "filters": [{"filter": f, "requests": used[f], "zero_match": zero[f]} for f in FILTER_FIELDS_PUBLIC if used[f]],
    }


GAP_KM = 10
GAP_MIN_PICKS = 5
GAP_MIN_DAYS = 3


def _km(lat1, lon1, lat2, lon2):
    import math

    dx = (lon2 - lon1) * math.cos(math.radians((lat1 + lat2) / 2))
    return math.hypot(lat2 - lat1, dx) * 111.19


def summarise_search_gaps(rows, spots):
    """Searched places that have no hitchhiking spot nearby (IDEAS #1255).

    rows: search_requests.csv dicts (timestamp, name, lat, lon). spots: iterable of (lat, lon).
    Keeps a 0.5 degree cell only when >= GAP_MIN_PICKS picks on >= GAP_MIN_DAYS days land in it
    and no spot lies within GAP_KM of the cell's mean pick. The label is the most common name,
    and only when it holds no digit (street addresses are dropped); no timestamps leave here.
    """
    from collections import Counter

    spots = list(spots)
    cells = defaultdict(lambda: {"n": 0, "days": set(), "lat": 0.0, "lon": 0.0, "names": Counter()})
    total = 0
    for row in rows:
        try:
            lat, lon = float(row["lat"]), float(row["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        day = (row.get("timestamp") or "")[:10]
        if not day:
            continue
        total += 1
        c = cells[_cell(lat, lon)]
        c["n"] += 1
        c["days"].add(day)
        c["lat"] += lat
        c["lon"] += lon
        name = (row.get("name") or "").strip()
        if name and not any(ch.isdigit() for ch in name):
            c["names"][name.split(",")[0].strip()] += 1
    out = []
    for cell, c in cells.items():
        if c["n"] < GAP_MIN_PICKS or len(c["days"]) < GAP_MIN_DAYS:
            continue
        lat, lon = c["lat"] / c["n"], c["lon"] / c["n"]
        if any(_km(lat, lon, s[0], s[1]) <= GAP_KM for s in spots):
            continue
        label = c["names"].most_common(1)[0][0] if c["names"] else None
        out.append({"cell": list(cell), "picks": c["n"], "days": len(c["days"]), "label": label})
    out.sort(key=lambda g: (-g["picks"], g["cell"]))
    return {"cell_deg": CELL_DEG, "gap_km": GAP_KM, "total_picks": total, "gaps": out[:100]}
