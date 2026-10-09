"""Per-city ride activity for the wiki's city articles (IDEAS #608).

cities.py hands in the rides that fall within a city's radius over the last 90 days;
the wiki's HitchabilityRating extension reads the resulting dist/place_activity.csv
(next to country_ratings.csv in the mounted export directory).
"""

import csv
import os
import statistics

# Below this a count is noise, and a wiki line saying "2 rides" would discourage more than inform.
ACTIVITY_MIN_RIDES = 5
# A median wait needs this many recorded waits behind it.
MIN_WAITS_FOR_MEDIAN = 5
COLUMNS = ["city", "country", "lat", "lon", "rides_90d", "median_wait_min"]


def activity_row(city, country, lat, lon, recent_waits):
    """recent_waits has one entry per recent ride: minutes waited, or None/NaN when not recorded."""
    waits = [w for w in recent_waits if w is not None and w == w and 0 <= w <= 600]
    median = round(statistics.median(waits)) if len(waits) >= MIN_WAITS_FOR_MEDIAN else ""
    return [city, country, round(float(lat), 4), round(float(lon), 4), len(recent_waits), median]


def write_place_activity_csv(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        w.writerows(sorted(rows, key=lambda r: (r[1], r[0])))
    os.replace(tmp, path)


COUNTRY_COLUMNS = ["country_code", "rides_90d", "median_wait_min"]
# A country line needs a clearly non-trivial count; the wiki also checks this.
COUNTRY_MIN_RIDES = 10


def country_activity_rows(recent_waits_by_cc):
    """recent_waits_by_cc: {cc: [wait minutes or None, one per ride in the window]} -> csv rows."""
    rows = []
    for cc, waits in recent_waits_by_cc.items():
        if len(waits) < COUNTRY_MIN_RIDES:
            continue
        ok = [w for w in waits if w is not None and w == w and 0 <= w <= 600]
        median = round(statistics.median(ok)) if len(ok) >= MIN_WAITS_FOR_MEDIAN else ""
        rows.append([cc.upper(), len(waits), median])
    return sorted(rows)


def write_country_activity_csv(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(COUNTRY_COLUMNS)
        w.writerows(rows)
    os.replace(tmp, path)


def write_activity_summary(path, rides_7d, rides_28d):
    """Site-wide counts for the wiki front page line (IDEAS #611)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["rides_7d", "rides_28d"])
        w.writerow([int(rides_7d), int(rides_28d)])
    os.replace(tmp, path)
