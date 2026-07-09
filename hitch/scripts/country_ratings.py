"""Obtain hitchwiki.org country ratings.

Computes the average hitchhiking-ride rating per country and writes it to a CSV.

Runs monthly via cron (see deploy/cron.sh) and can also be triggered by hand:

    flask --app hitch generate country_ratings   # how cron invokes it
    python hitch/scripts/country_ratings.py       # standalone, equivalent

Each ride's country is derived from its start coordinate (stops[0].location)
via offline reverse geocoding (the `reverse_geocoder` package — no API calls,
no network).

Outputs:
  - dist/country_ratings.csv  — one row per country, sorted by hitchability
    (descending). Columns: country_code, hitchability (0–5 composite score, see
    the Hitchability block below), average_rating, ride_count, average_distance_km,
    average_wait_min, wait_min_per_km, rides_per_1000km2, distance_wait_ride_count.
  - dist/country_ratings.json — {cc: {rating, count, hitch}}, consumed by the map's
    "Countries" mode. `rating` still drives the current choropleth colour; `hitch`
    is the new 0–5 hitchability score (omitted for countries that can't be scored).
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
from datetime import datetime, timedelta

import reverse_geocoder as rg

# Resolve the DB path the same way hitch/settings.py does: db/{DATABASE_NAME}.
# Defaults to the production DB name so a manual run on the server just works.
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATABASE_NAME = os.getenv("DATABASE_NAME", "hitchhiking-prod.sqlite")
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
# A country needs at least this many rides before it gets a colour on the map
# and its own statistics; below it the sample is too small to be meaningful.
MIN_RIDES_FOR_STATS = 25
# The choropleth colour reflects only recent experience: the average rating is
# computed from rides submitted within this many years.
RATING_WINDOW_YEARS = 3

# --- Hitchability score --------------------------------------------------------
# A single 0–5 "how hitchable is this country" score combining three signals:
#   1. efficiency  — low waiting-time-per-km-travelled is good (short waits, long lifts)
#   2. density     — many rides logged per km² of land area (a well-mapped, active scene)
#   3. rating      — average spot rating (kept a MINOR input: people rate almost
#                    everything 4/5, so it barely discriminates)
# Each signal is z-scored against a frozen reference distribution (the constants
# below, computed once over the 58-country pool on 2026-07 data), combined with
# the intent weights, then affine-mapped to 0–5. Freezing the reference means a
# country's score depends only on its own metrics, not on which other countries
# happen to have data this run.
#
# Calibration anchors (rough guidance from the maintainer): EE≈5, DE/FR/NL≈4,
# IT/ES≈3. SCORE_BASE/SLOPE were least-squares fit to those anchors; the current
# constants reproduce EE 4.9, DE 4.1, FR 4.2, NL 3.8, IT 3.1, ES 3.0.
HITCH_WEIGHT_EFFICIENCY = 0.40
HITCH_WEIGHT_DENSITY = 0.40
HITCH_WEIGHT_RATING = 0.20
# z-score reference: mean/stdev of each signal across the frozen country pool.
# Efficiency signal is -wait_per_km; density signal is log10(rides per 1000 km²).
HITCH_EFF_MEAN, HITCH_EFF_SD = -0.4225, 0.1751
HITCH_DENS_MEAN, HITCH_DENS_SD = 0.4637, 0.9796
HITCH_RAT_MEAN, HITCH_RAT_SD = 3.9127, 0.2351
# Affine map from the weighted-z composite to the 0–5 score.
HITCH_SCORE_BASE, HITCH_SCORE_SLOPE = 3.810, 1.072

# Land area in km² per ISO-3166-1 alpha-2 code, used for the ride-density signal.
# Only countries listed here get a hitchability score (density is undefined
# without an area); extend as new countries gather enough rides.
COUNTRY_AREA_KM2 = {
    "EE": 45227,
    "DE": 357022,
    "FR": 551695,
    "NL": 41850,
    "IT": 301340,
    "ES": 505990,
    "PL": 312696,
    "CZ": 78865,
    "AT": 83879,
    "BE": 30528,
    "CH": 41285,
    "SE": 450295,
    "FI": 338424,
    "NO": 385207,
    "DK": 43094,
    "GB": 242495,
    "PT": 92090,
    "RO": 238397,
    "HU": 93028,
    "SK": 49035,
    "LT": 65300,
    "LV": 64559,
    "HR": 56594,
    "SI": 20273,
    "GR": 131957,
    "IE": 70273,
    "BG": 110879,
    "RS": 88361,
    "UA": 603500,
    "BY": 207600,
    "MD": 33846,
    "AL": 28748,
    "MK": 25713,
    "BA": 51197,
    "ME": 13812,
    "LU": 2586,
    "IS": 103000,
    "TR": 783562,
    "RU": 17098246,
    "US": 9833517,
    "CA": 9984670,
    "AU": 7692024,
    "NZ": 268021,
    "MX": 1964375,
    "BR": 8515767,
    "AR": 2780400,
    "MA": 446550,
    "IN": 3287263,
    "TH": 513120,
    "VN": 331212,
    "ID": 1904569,
    "CL": 756102,
    "PE": 1285216,
    "CO": 1141748,
    "GE": 69700,
    "AM": 29743,
    "IR": 1648195,
    "IL": 20770,
    "JO": 89342,
    "JP": 377975,
    "TW": 36197,
    "PH": 300000,
    "KG": 199951,
    "KZ": 2724900,
    "XK": 10887,
    "CN": 9596961,
    "TJ": 143100,
    "NA": 825615,
    "MY": 330803,
    "LA": 236800,
    "AD": 468,
    "KH": 181035,
    "ZA": 1221037,
}


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


def paired_averages(pairs):
    """Average wait (min), distance (km) and wait-per-km over (wait, distance) pairs.

    Only rides that have both metrics are passed in. Large outliers are dropped
    before averaging: a pair is kept only if BOTH its wait and its distance fall
    within mean ± OUTLIER_STDEVS·stdev of their respective distributions (same
    clipping rule as the histograms). Returns None when there's nothing to report.
    """
    if not pairs:
        return None
    waits = [w for w, _ in pairs]
    dists = [d for _, d in pairs]
    ws = compute_stats(waits)
    ds = compute_stats(dists)

    def bounds(st):
        # No spread (or a single sample) → don't clip.
        if not st or not (st["stdev"] > 0):
            return float("-inf"), float("inf")
        return st["mean"] - OUTLIER_STDEVS * st["stdev"], st["mean"] + OUTLIER_STDEVS * st["stdev"]

    wlo, whi = bounds(ws)
    dlo, dhi = bounds(ds)
    kept = [(w, d) for w, d in pairs if wlo <= w <= whi and dlo <= d <= dhi]
    if not kept:
        return None
    n = len(kept)
    avg_wait = sum(w for w, _ in kept) / n
    avg_dist = sum(d for _, d in kept) / n
    # Waiting time per km travelled: minutes spent waiting per km covered, taken
    # as total wait over total distance (equivalently avg_wait / avg_distance).
    wait_per_km = avg_wait / avg_dist if avg_dist > 0 else None
    return {"avg_wait": avg_wait, "avg_distance": avg_dist, "wait_per_km": wait_per_km, "n": n}


def hitchability_score(wait_per_km, density_per_1000km2, rating):
    """Combine the three signals into a 0–5 hitchability score (see the constants block).

    Returns None if the efficiency signal is missing (a country with no rides that
    have both a wait and a distance can't be scored). A missing rating falls back
    to the reference mean so it contributes nothing rather than blowing up.
    """
    if wait_per_km is None or density_per_1000km2 is None or density_per_1000km2 <= 0:
        return None
    z_eff = (-wait_per_km - HITCH_EFF_MEAN) / HITCH_EFF_SD
    z_dens = (math.log10(density_per_1000km2) - HITCH_DENS_MEAN) / HITCH_DENS_SD
    z_rat = ((rating if rating is not None else HITCH_RAT_MEAN) - HITCH_RAT_MEAN) / HITCH_RAT_SD
    composite = HITCH_WEIGHT_EFFICIENCY * z_eff + HITCH_WEIGHT_DENSITY * z_dens + HITCH_WEIGHT_RATING * z_rat
    score = HITCH_SCORE_BASE + HITCH_SCORE_SLOPE * composite
    return max(0.0, min(5.0, score))


def is_recent(submission_time, cutoff):
    """True if submission_time (ISO string) is on/after cutoff. Unknown dates → False."""
    if not isinstance(submission_time, str):
        return False
    try:
        return datetime.fromisoformat(submission_time) >= cutoff
    except ValueError:
        return False


def main():
    conn = sqlite3.connect(DATABASE_URI)
    rows = conn.execute("SELECT stops, rating, submission_time FROM ride_event").fetchall()
    conn.close()

    # The rating average only reflects rides from the last RATING_WINDOW_YEARS.
    rating_cutoff = datetime.now() - timedelta(days=365.25 * RATING_WINDOW_YEARS)

    coords = []
    # Per-ride metrics, index-aligned with `coords` so we can group by country
    # after the batched reverse-geocode.
    per_ride = []
    for stops, rating, submission_time in rows:
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

        per_ride.append(
            {
                # Only recent ratings feed the colour; older ones are ignored.
                "rating": rating if is_recent(submission_time, rating_cutoff) else None,
                # Hitchability uses the all-time average rating (its calibration
                # was fit that way), independent of the recency window above.
                "raw_rating": rating,
                "wait": parse_wait_minutes(stops[0]),
                "distance": distance,
            }
        )

    # Single batched, offline reverse-geocode of every start coordinate.
    results = rg.search(coords)

    sums = defaultdict(float)
    counts = defaultdict(int)
    totals = defaultdict(int)
    waits = defaultdict(list)
    distances = defaultdict(list)
    # All-time rating (for hitchability, which is calibrated on the full history).
    raw_rating_sums = defaultdict(float)
    raw_rating_counts = defaultdict(int)
    # Rides that have BOTH a waiting time and a distance, as (wait, distance)
    # pairs — the basis for average distance / wait / wait-per-km / efficiency.
    paired = defaultdict(list)
    for res, ride in zip(results, per_ride):
        cc = res["cc"]
        # Every placed ride counts toward the country's total (the MIN_RIDES_FOR_STATS gate).
        totals[cc] += 1
        # Ratings feed the choropleth; only count rides that actually have one.
        if ride["rating"] is not None:
            sums[cc] += ride["rating"]
            counts[cc] += 1
        if ride["raw_rating"] is not None:
            raw_rating_sums[cc] += ride["raw_rating"]
            raw_rating_counts[cc] += 1
        if ride["wait"] is not None and ride["wait"] >= 0:
            waits[cc].append(ride["wait"])
        if ride["distance"] is not None:
            distances[cc].append(ride["distance"])
        if ride["wait"] is not None and ride["wait"] >= 0 and ride["distance"] is not None:
            paired[cc].append((ride["wait"], ride["distance"]))

    # Only surface countries with enough rides to be meaningful.
    rated_ccs = {cc for cc in sums if totals[cc] >= MIN_RIDES_FOR_STATS}

    # Per-country hitchability inputs + score, keyed by cc (None when unscorable).
    def build_hitchability(cc):
        pa = paired_averages(paired[cc])
        area = COUNTRY_AREA_KM2.get(cc)
        density = totals[cc] / area * 1000.0 if area else None  # rides per 1000 km²
        raw_rating = raw_rating_sums[cc] / raw_rating_counts[cc] if raw_rating_counts[cc] else None
        wpk = pa["wait_per_km"] if pa else None
        score = hitchability_score(wpk, density, raw_rating)
        return pa, density, raw_rating, wpk, score

    country_rows = []
    for cc in rated_ccs:
        pa, density, raw_rating, wpk, score = build_hitchability(cc)
        country_rows.append(
            (
                cc,
                round(sums[cc] / counts[cc]),
                counts[cc],
                round(score, 1) if score is not None else "",
                round(pa["avg_distance"], 1) if pa else "",
                round(pa["avg_wait"], 1) if pa else "",
                round(wpk, 2) if wpk is not None else "",
                round(density, 3) if density is not None else "",
                pa["n"] if pa else 0,
            )
        )
    # Sort by hitchability (desc), then average rating, then ride count as tiebreaks.
    # Unscored countries ("" hitchability) sort to the bottom.
    country_rows.sort(key=lambda r: (r[3] if r[3] != "" else -1, r[1], r[2]), reverse=True)

    os.makedirs(DIST_DIR, exist_ok=True)
    with open(OUTPUT_CSV, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "country_code",
                "hitchability",
                "average_rating",
                "ride_count",
                "average_distance_km",
                "average_wait_min",
                "wait_min_per_km",
                "rides_per_1000km2",
                "distance_wait_ride_count",
            ]
        )
        for cc, rating, count, score, avg_dist, avg_wait, wpk, density, pair_n in country_rows:
            writer.writerow([cc, score, rating, count, avg_dist, avg_wait, wpk, density, pair_n])

    # Same data keyed by country code for the map's "Countries" overlay. `hitch`
    # is the 0–5 hitchability score (omitted when the country can't be scored).
    ratings_by_cc = {}
    for cc, rating, count, score, *_ in country_rows:
        entry = {"rating": rating, "count": count}
        if score != "":
            entry["hitch"] = score
        ratings_by_cc[cc] = entry
    with open(OUTPUT_JSON, "w") as f:
        json.dump(ratings_by_cc, f)

    # Pre-computed waiting-time / distance histograms, only for countries that
    # clear the ride threshold (same gate as the choropleth colour).
    insights_by_cc = {}
    for cc in set(waits) | set(distances):
        if totals[cc] < MIN_RIDES_FOR_STATS:
            continue
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


# Run on import too, so `flask --app hitch generate country_ratings` works (the
# generate command executes scripts by importing them). Also runnable directly
# via `python hitch/scripts/country_ratings.py`.
main()
