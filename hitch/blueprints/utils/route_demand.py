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
