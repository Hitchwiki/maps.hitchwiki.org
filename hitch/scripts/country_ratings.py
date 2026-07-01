"""Obtain hitchwiki.org country ratings.

Computes the average hitchhiking-ride rating per country and writes it to a CSV.

This is a standalone, manually-triggered script (NOT wired into cron or
`flask generate`). Run it by hand whenever fresh country ratings are needed:

    python hitch/scripts/country_ratings.py

Each ride's country is derived from its start coordinate (stops[0].location)
via offline reverse geocoding (the `reverse_geocoder` package — no API calls,
no network).

Outputs:
  - dist/country_ratings.csv  — sorted by average rating (descending)
  - dist/country_ratings.json — {cc: {rating, count}}, consumed by the map's
    "Countries" mode to colour each country by its rating
  - dist/country_insights.json — {cc: {wait, distance}} where each metric holds
    a PRE-COMPUTED histogram {stats, hidden, hist:{lo, hi, binWidth, counts}} for
    waiting time (minutes) and ride distance (km). The binning/clipping/stats
    mirror the client's /insights view (see map.js computeHistogram /
    clipForHistogram / computeStats) so the country sheet can draw the exact same
    charts instantly, without shipping the raw per-ride samples.
"""

import csv
import json
import math
import os
import sqlite3
from collections import defaultdict

import reverse_geocoder as rg

# Resolve the DB path the same way hitch/settings.py does: db/{DATABASE_NAME}.
# Defaults to the production DB name so a manual run on the server just works.
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATABASE_NAME = os.getenv("DATABASE_NAME", "prod-points.sqlite")
DATABASE_URI = os.getenv("DATABASE_URI", os.path.join(BASE_DIR, "db", DATABASE_NAME))

DIST_DIR = os.path.join(BASE_DIR, "dist")
OUTPUT_CSV = os.path.join(DIST_DIR, "country_ratings.csv")
OUTPUT_JSON = os.path.join(DIST_DIR, "country_ratings.json")
OUTPUT_INSIGHTS = os.path.join(DIST_DIR, "country_insights.json")

# Rides shorter than this (km) are treated as having no destination, matching
# show.py's "unrealistically short" cleaning so the two views agree.
MIN_RIDE_DISTANCE_KM = 1
# Histogram bars are clipped to mean ± this many std devs (matches map.js
# INSIGHTS_OUTLIER_STDEVS) so a few outliers don't squash the distribution.
OUTLIER_STDEVS = 3


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance in km (same earth radius as show.py's haversine_np)."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def parse_wait_minutes(start_stop):
    """Parse an ISO-8601 'PT<mins>M' waiting_duration into minutes (matches show.py).

    Note: waiting_duration lives on the stop object itself, not on its nested
    `location` (see show.py get_wait).
    """
    wait = start_stop.get("waiting_duration")
    if not isinstance(wait, str):
        return None
    try:
        return int(wait.replace("PT", "").replace("M", ""))
    except ValueError:
        return None


# --- Histogram maths, ported verbatim from map.js so the precomputed charts match
# the client's /insights view exactly. ---------------------------------------


def compute_stats(values):
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    mean = sum(s) / n
    median = s[(n - 1) // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2
    variance = sum((v - mean) ** 2 for v in s) / (n - 1) if n > 1 else 0
    stdev = math.sqrt(variance)
    return {"n": n, "mean": mean, "median": median, "stdev": stdev, "min": s[0], "max": s[-1]}


def clip_for_histogram(values):
    """Return (kept, hidden): values within mean ± OUTLIER_STDEVS·stdev, and the drop count."""
    if not values or len(values) < 2:
        return list(values), 0
    st = compute_stats(values)
    if not st or not (st["stdev"] > 0):
        return list(values), 0
    lo = st["mean"] - OUTLIER_STDEVS * st["stdev"]
    hi = st["mean"] + OUTLIER_STDEVS * st["stdev"]
    kept = [v for v in values if lo <= v <= hi]
    return kept, len(values) - len(kept)


def choose_bins(sorted_values):
    """Freedman–Diaconis bin count with a Sturges fallback, clamped to [8, 40]."""
    n = len(sorted_values)
    if n < 2:
        return 1
    q1 = sorted_values[int((n - 1) * 0.25)]
    q3 = sorted_values[int((n - 1) * 0.75)]
    iqr = q3 - q1
    rng = sorted_values[-1] - sorted_values[0]
    if rng == 0:
        return 1
    if iqr > 0:
        width = (2 * iqr) / (n ** (1 / 3))
        bins = math.ceil(rng / width)
    else:
        bins = math.ceil(math.log2(n) + 1)
    return max(8, min(40, bins))


def nice_step(raw_step):
    """Pick a 'nice' step (1, 2, 2.5, 5 × 10^k)."""
    if raw_step <= 0:
        return 1
    exp = math.floor(math.log10(raw_step))
    frac = raw_step / (10**exp)
    if frac < 1.5:
        nice = 1
    elif frac < 3:
        nice = 2
    elif frac < 4:
        nice = 2.5
    elif frac < 7:
        nice = 5
    else:
        nice = 10
    return nice * (10**exp)


def compute_histogram(values):
    """Bin `values` into {lo, hi, binWidth, counts}, matching map.js computeHistogram."""
    if not values:
        return None
    s = sorted(values)
    mn, mx = s[0], s[-1]
    bins = choose_bins(s)
    bin_width = (mx - mn) / bins
    lo, hi = mn, mx
    if bin_width == 0:
        bin_width, lo, hi, bins = 1, mn - 0.5, mx + 0.5, 1
    else:
        bin_width = nice_step(bin_width)
        lo = math.floor(mn / bin_width) * bin_width
        hi = math.ceil(mx / bin_width) * bin_width
        if hi == lo:
            hi = lo + bin_width
        bins = round((hi - lo) / bin_width)
    counts = [0] * bins
    for v in s:
        idx = math.floor((v - lo) / bin_width)
        idx = min(max(idx, 0), bins - 1)
        counts[idx] += 1
    return {
        "lo": round(lo, 3),
        "hi": round(hi, 3),
        "binWidth": round(bin_width, 3),
        "counts": counts,
    }


def build_metric(values):
    """Precompute the full-sample stats, outlier-hidden count, and clipped histogram."""
    if not values:
        return None
    stats = compute_stats(values)
    kept, hidden = clip_for_histogram(values)
    hist = compute_histogram(kept)
    if hist is None:
        return None
    return {
        "stats": {
            "n": stats["n"],
            "mean": round(stats["mean"], 3),
            "median": round(stats["median"], 3),
            "stdev": round(stats["stdev"], 3),
            "min": round(stats["min"], 3),
            "max": round(stats["max"], 3),
        },
        "hidden": hidden,
        "hist": hist,
    }


def main():
    conn = sqlite3.connect(DATABASE_URI)
    rows = conn.execute("SELECT stops, rating FROM ride_event").fetchall()
    conn.close()

    coords = []
    # Per-ride metrics, index-aligned with `coords` so we can group by country
    # after the batched reverse-geocode.
    per_ride = []
    for stops, rating in rows:
        stops = json.loads(stops) if isinstance(stops, str) else stops
        # Skip rides we can't place (missing/malformed start location).
        try:
            start = stops[0]["location"]
            slat, slon = start["latitude"], start["longitude"]
        except (TypeError, KeyError, IndexError):
            continue
        coords.append((slat, slon))

        # Ride distance: great-circle from start to the last stop, dropped when
        # under MIN_RIDE_DISTANCE_KM (same cleaning as show.py).
        distance = None
        if isinstance(stops, list) and len(stops) > 1:
            try:
                end = stops[-1]["location"]
                d = haversine_km(slat, slon, end["latitude"], end["longitude"])
                if d >= MIN_RIDE_DISTANCE_KM:
                    distance = round(d, 1)
            except (TypeError, KeyError, IndexError):
                pass

        per_ride.append({"rating": rating, "wait": parse_wait_minutes(stops[0]), "distance": distance})

    # Single batched, offline reverse-geocode of every start coordinate.
    results = rg.search(coords)

    sums = defaultdict(float)
    counts = defaultdict(int)
    waits = defaultdict(list)
    distances = defaultdict(list)
    for res, ride in zip(results, per_ride):
        cc = res["cc"]
        # Ratings feed the choropleth; only count rides that actually have one.
        if ride["rating"] is not None:
            sums[cc] += ride["rating"]
            counts[cc] += 1
        if ride["wait"] is not None and ride["wait"] >= 0:
            waits[cc].append(ride["wait"])
        if ride["distance"] is not None:
            distances[cc].append(ride["distance"])

    country_rows = [
        (cc, round(sums[cc] / counts[cc]), counts[cc]) for cc in sums
    ]
    # Sort by average rating (desc), then by number of rides (desc) as tiebreak.
    country_rows.sort(key=lambda r: (r[1], r[2]), reverse=True)

    os.makedirs(DIST_DIR, exist_ok=True)
    with open(OUTPUT_CSV, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["country_code", "average_rating", "ride_count"])
        writer.writerows(country_rows)

    # Same data keyed by country code for the map's "Countries" overlay.
    ratings_by_cc = {cc: {"rating": rating, "count": count} for cc, rating, count in country_rows}
    with open(OUTPUT_JSON, "w") as f:
        json.dump(ratings_by_cc, f)

    # Pre-computed waiting-time / distance histograms per country for the sheet.
    insights_by_cc = {}
    for cc in set(waits) | set(distances):
        metrics = {}
        wait_metric = build_metric(waits[cc])
        dist_metric = build_metric(distances[cc])
        if wait_metric:
            metrics["wait"] = wait_metric
        if dist_metric:
            metrics["distance"] = dist_metric
        if metrics:
            insights_by_cc[cc] = metrics
    with open(OUTPUT_INSIGHTS, "w") as f:
        json.dump(insights_by_cc, f)

    print(
        f"Wrote {len(country_rows)} countries ({sum(counts.values())} rides) to {OUTPUT_CSV} and {OUTPUT_JSON}; "
        f"insights for {len(insights_by_cc)} countries to {OUTPUT_INSIGHTS}"
    )


if __name__ == "__main__":
    main()
